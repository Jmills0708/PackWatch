"""
PackWatch scraper engine
-------------------------
Pulls sealed-product listings for anime TCGs (One Piece, Pokémon, Union Arena,
Dragon Ball, Naruto) from a set of pluggable "sources," normalizes them into a
common schema, and writes them to a SQLite database that the API layer reads.

Design notes:
- Each source is a small adapter class with a `.fetch()` method that returns a
  list of normalized dicts. This keeps the scraper resilient: if one retailer
  changes their page layout, only that adapter breaks, not the whole system.
- Prefer official APIs over HTML scraping wherever they exist:
  * TCGPlayer has a public Catalog + Pricing API (requires a free developer
    key: https://docs.tcgplayer.com/docs).
  * eBay has the Browse API for completed/active listings.
  * Retailers without an API (small local game stores, Premium Bandai, etc.)
    are the ones you'd scrape directly — check robots.txt and Terms of
    Service before doing so, and keep request rates low (see run() below).
- This file ships with:
  1. A working TCGPlayer adapter (uses their public API — swap in your key).
  2. A generic HTML adapter you can configure per-retailer with CSS
     selectors, for sites that allow it.
  3. A mock adapter so you can run this end-to-end with no credentials.
"""

import os
import re
import time
import sqlite3
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional

import requests

from affiliate import affiliate_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("packwatch")

DB_PATH = os.environ.get("PACKWATCH_DB", "packwatch.db")
REQUEST_DELAY_SECONDS = 2.0  # be polite; raise this if a source asks for it


@dataclass
class Listing:
    game: str
    set_name: str
    product: str
    retailer: str
    price: float
    shipping: float
    msrp: Optional[float]
    url: str
    status: str  # preorder_open | preorder_soon | in_stock | low_stock
    release_date: Optional[str]  # ISO date, if known
    fetched_at: str


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL,
            set_name TEXT NOT NULL,
            product TEXT NOT NULL,
            retailer TEXT NOT NULL,
            price REAL NOT NULL,
            shipping REAL NOT NULL DEFAULT 0,
            msrp REAL,
            url TEXT,
            status TEXT,
            release_date TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE(game, set_name, product, retailer)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts_sent (
            listing_key TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        )
        """
    )
    # Append-only log of every observed (status, price) per listing per run.
    # The notifier diffs the last two rows per listing_key to catch a
    # preorder opening or a price drop, without needing to hold scraper
    # state in memory between separate workflow steps.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listings_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_key TEXT NOT NULL,
            game TEXT NOT NULL,
            set_name TEXT NOT NULL,
            product TEXT NOT NULL,
            retailer TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _listing_key(item: Listing) -> str:
    return "|".join([item.game, item.set_name, item.product, item.retailer])


def upsert_listings(conn, listings: List[Listing]):
    for item in listings:
        item.url = affiliate_link(item.url, item.retailer)
        conn.execute(
            """
            INSERT INTO listings (game, set_name, product, retailer, price, shipping, msrp, url, status, release_date, fetched_at)
            VALUES (:game, :set_name, :product, :retailer, :price, :shipping, :msrp, :url, :status, :release_date, :fetched_at)
            ON CONFLICT(game, set_name, product, retailer) DO UPDATE SET
                price=excluded.price,
                shipping=excluded.shipping,
                msrp=excluded.msrp,
                url=excluded.url,
                status=excluded.status,
                release_date=excluded.release_date,
                fetched_at=excluded.fetched_at
            """,
            asdict(item),
        )
        conn.execute(
            """
            INSERT INTO listings_history (listing_key, game, set_name, product, retailer, price, status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_listing_key(item), item.game, item.set_name, item.product, item.retailer, item.price, item.status, item.fetched_at),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

class TCGPlayerAdapter:
    """
    Uses TCGPlayer's public API. Sign up for a free key at
    https://docs.tcgplayer.com/docs and set TCGPLAYER_API_KEY.
    This adapter is illustrative — TCGPlayer's exact endpoints/auth flow
    (OAuth bearer token) should be confirmed against their current docs.
    """

    BASE_URL = "https://api.tcgplayer.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TCGPLAYER_API_KEY")

    def fetch(self, game_category_id: int, game_name: str) -> List[Listing]:
        if not self.api_key:
            log.warning("No TCGPLAYER_API_KEY set — skipping TCGPlayer adapter for %s", game_name)
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.get(
                f"{self.BASE_URL}/catalog/categories/{game_category_id}/search",
                headers=headers,
                params={"limit": 20, "sort": "releaseDate desc"},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("TCGPlayer fetch failed for %s: %s", game_name, exc)
            return []

        results = []
        for product in resp.json().get("results", []):
            results.append(
                Listing(
                    game=game_name,
                    set_name=product.get("groupName", "Unknown set"),
                    product=product.get("name", "Sealed product"),
                    retailer="TCGPlayer",
                    price=float(product.get("marketPrice") or 0),
                    shipping=0.0,
                    msrp=float(product.get("msrp") or 0) or None,
                    url=product.get("url", ""),
                    status="in_stock",
                    release_date=product.get("releaseDate"),
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return results


class GenericHTMLAdapter:
    """
    Configurable scraper for a single retailer page. Provide CSS selectors for
    each field. Check the site's robots.txt and Terms of Service before
    enabling this for a given retailer — some explicitly prohibit scraping.
    Requires: pip install beautifulsoup4
    """

    def __init__(self, retailer: str, url: str, game: str, selectors: dict):
        self.retailer = retailer
        self.url = url
        self.game = game
        self.selectors = selectors  # e.g. {"card": ".product-card", "name": ".title", "price": ".price"}

    def fetch(self) -> List[Listing]:
        from bs4 import BeautifulSoup  # local import so the file runs without bs4 installed

        try:
            resp = requests.get(self.url, timeout=15, headers={"User-Agent": "PackWatchBot/1.0 (+contact@example.com)"})
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("%s fetch failed: %s", self.retailer, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        listings = []
        for card in soup.select(self.selectors["card"]):
            try:
                name = card.select_one(self.selectors["name"]).get_text(strip=True)
                price_text = card.select_one(self.selectors["price"]).get_text(strip=True)
                # Some themes concatenate a struck-through "was" price with the
                # current price in the same element (e.g. "$8.00$6.80"). The
                # current price is always the last $-prefixed amount present.
                price_matches = re.findall(r"\$[\d,]+\.?\d*", price_text)
                price = float(price_matches[-1].replace("$", "").replace(",", "")) if price_matches else float(
                    price_text.replace("$", "").replace(",", "")
                )
                link_el = card.select_one(self.selectors.get("link", "a"))
                link = link_el["href"] if link_el and link_el.has_attr("href") else self.url
                if link.startswith("/"):
                    link = self.base_url + link
            except (AttributeError, ValueError):
                continue
            listings.append(
                Listing(
                    game=self.game,
                    set_name=name,
                    product=name,
                    retailer=self.retailer,
                    price=price,
                    shipping=0.0,
                    msrp=None,
                    url=link,
                    status="in_stock",
                    release_date=None,
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return listings

    @property
    def base_url(self) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(self.url)
        return f"{parts.scheme}://{parts.netloc}"


class MockAdapter:
    """Deterministic sample data so the pipeline runs with zero setup."""

    def fetch(self) -> List[Listing]:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            ("One Piece", "OP-17 The Four Emperors", "Booster Box (24 packs)", "Gamers Guild AZ", 104.99, 0, 119.76, "preorder_open", "2026-08-26", "https://gamersguildaz.com/collections/one-piece-tcg"),
            ("Pokémon", "Storm Emerald (JP)", "Booster Box", "TCGPlayer", 84.0, 0, 99.99, "preorder_open", "2026-08-07", "https://www.tcgplayer.com/search/pokemon/product?q=Storm+Emerald"),
            ("Union Arena", "InuYasha [UA50BT]", "Booster Box", "N4YTCG", 74.99, 0, 79.99, "preorder_open", "2026-08-14", "https://www.n4ytcg.com/collections/union-arena"),
        ]
        return [
            Listing(game=g, set_name=s, product=p, retailer=r, price=pr, shipping=sh, msrp=m, url=u, status=st, release_date=rd, fetched_at=now)
            for g, s, p, r, pr, sh, m, st, rd, u in rows
        ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    conn = init_db()

    tcg = TCGPlayerAdapter()

    # TCGPlayer category IDs, confirmed against TCGPlayer's public catalog
    # (tcgcsv.com/tcgplayer/categories) on 2026-07-30:
    #   Pokemon (English) = 3, Pokemon Japan = 85, One Piece Card Game = 68,
    #   Dragon Ball Super: Fusion World = 80, Union Arena = 81.
    # TCGPlayer has no distinct Naruto TCG category — that game relies on the
    # GenericHTMLAdapter entries below instead. Each of these is a zero-arg
    # callable so run() can pace requests between them (see the loop below);
    # they no-op and return [] until TCGPLAYER_API_KEY is set as a repo secret.
    sources = [
        MockAdapter(),
        lambda: tcg.fetch(game_category_id=3, game_name="Pokémon"),
        lambda: tcg.fetch(game_category_id=85, game_name="Pokémon"),
        lambda: tcg.fetch(game_category_id=68, game_name="One Piece"),
        lambda: tcg.fetch(game_category_id=80, game_name="Dragon Ball Super"),
        lambda: tcg.fetch(game_category_id=81, game_name="Union Arena"),
        # Gamers Guild AZ — small Phoenix-area LGS with a public storefront.
        # Selectors confirmed by hand against their live collection pages.
        GenericHTMLAdapter(
            retailer="Gamers Guild AZ",
            url="https://gamersguildaz.com/collections/one-piece-tcg",
            game="One Piece",
            selectors={"card": "ul#collection li", "name": "h3.p0 a", "price": "p.price", "link": "h3.p0 a"},
        ),
        GenericHTMLAdapter(
            retailer="Gamers Guild AZ",
            url="https://gamersguildaz.com/collections/pokemon-sealed-product",
            game="Pokémon",
            selectors={"card": "ul#collection li", "name": "h3.p0 a", "price": "p.price", "link": "h3.p0 a"},
        ),
        GenericHTMLAdapter(
            retailer="Gamers Guild AZ",
            url="https://gamersguildaz.com/collections/union-arena",
            game="Union Arena",
            selectors={"card": "ul#collection li", "name": "h3.p0 a", "price": "p.price", "link": "h3.p0 a"},
        ),
        GenericHTMLAdapter(
            retailer="Gamers Guild AZ",
            url="https://gamersguildaz.com/collections/dragon-ball-super",
            game="Dragon Ball Super",
            selectors={"card": "ul#collection li", "name": "h3.p0 a", "price": "p.price", "link": "h3.p0 a"},
        ),
        # N4YTCG — sealed-product specialist, Shopify storefront.
        GenericHTMLAdapter(
            retailer="N4YTCG",
            url="https://www.n4ytcg.com/collections/pokemon",
            game="Pokémon",
            selectors={"card": "li.grid__item .card-wrapper", "name": ".card__heading a", "price": ".price-item--regular", "link": ".card__heading a"},
        ),
        GenericHTMLAdapter(
            retailer="N4YTCG",
            url="https://www.n4ytcg.com/collections/union-arena",
            game="Union Arena",
            selectors={"card": "li.grid__item .card-wrapper", "name": ".card__heading a", "price": ".price-item--regular", "link": ".card__heading a"},
        ),
        # No retailer configured yet for Naruto TCG — TCGPlayer doesn't carry
        # it as a distinct category, and neither small shop above lists it.
        # Add a GenericHTMLAdapter here once a source is found.
    ]

    all_listings: List[Listing] = []
    for source in sources:
        try:
            if hasattr(source, "fetch") and not isinstance(source, list):
                items = source.fetch()
            elif callable(source):
                items = source()
            else:
                items = source
            all_listings.extend(items)
        except Exception as exc:  # keep one bad source from killing the whole run
            log.error("Source failed: %s", exc)
        time.sleep(REQUEST_DELAY_SECONDS)

    log.info("Collected %d listings", len(all_listings))
    upsert_listings(conn, all_listings)
    conn.close()


if __name__ == "__main__":
    run()
