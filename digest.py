"""
PackWatch daily digest
-----------------------
Unlike notifier.py (which only posts when something *changes*), this posts a
standing summary of everything currently in the listings table — a "here's
what's out there right now" roundup. Meant to run once a day, separately
from the 30-minute scrape/alert cycle.

Groups by game, shows the best deal per game plus anything with an open
preorder, and keeps the message short enough to be actually read.
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone
from collections import defaultdict

import requests

from signals import buy_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("packwatch.digest")

DB_PATH = os.environ.get("PACKWATCH_DB", "packwatch.db")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MAX_ITEMS_PER_GAME = 3  # keep the digest scannable


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def deal_pct(price, msrp):
    if not msrp or msrp <= 0:
        return 0
    return round((msrp - price) / msrp * 100)


def build_digest(conn) -> str:
    rows = conn.execute("SELECT * FROM listings ORDER BY fetched_at DESC").fetchall()
    if not rows:
        return "📋 **PackWatch Daily Digest** — no listings tracked yet. Check the scraper's sources."

    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game"]].append(dict(r))

    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    lines = [f"📋 **PackWatch Daily Digest — {today}**", ""]

    for game in sorted(by_game.keys()):
        items = by_game[game]
        items.sort(key=lambda d: deal_pct(d["price"], d.get("msrp")), reverse=True)
        lines.append(f"**{game}**")
        for item in items[:MAX_ITEMS_PER_GAME]:
            pct = deal_pct(item["price"], item.get("msrp"))
            signal, reason = buy_signal(item["price"], item.get("shipping", 0), item.get("msrp"), item["status"])
            circle = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[signal]
            price_line = f"${item['price']:.2f}"
            if pct > 0:
                price_line += f" ({pct}% under MSRP)"
            lines.append(f"{circle} {item['set_name']} — {price_line} @ {item['retailer']}")
            lines.append(f"   _{reason}_")
        lines.append("")

    lines.append(f"_Tracking {len(rows)} listing(s) across {len(by_game)} game(s)._")
    return "\n".join(lines)


def send_discord_digest(message: str):
    if not DISCORD_WEBHOOK_URL:
        log.warning("No DISCORD_WEBHOOK_URL set — printing instead of sending:\n%s", message)
        return
    # Discord caps messages at 2000 characters — split if needed.
    for chunk_start in range(0, len(message), 1900):
        chunk = message[chunk_start:chunk_start + 1900]
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk}, timeout=10)
        except requests.RequestException as exc:
            log.error("Failed to send digest chunk: %s", exc)


def run():
    conn = get_conn()
    message = build_digest(conn)
    send_discord_digest(message)
    conn.close()
    log.info("Digest sent (%d chars)", len(message))


if __name__ == "__main__":
    run()
