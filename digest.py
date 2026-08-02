"""
PackWatch daily digest
-----------------------
Unlike notifier.py (which only posts when something *changes*), this posts a
standing summary of everything currently in the listings table — a "here's
what's out there right now" roundup.

Runs hourly. To keep hourly runs from re-spamming the channel with the same
~200-listing roundup over and over, this only actually posts to Discord when
the underlying listing content has changed since the last successful send
(tracked via a small digest_state table in packwatch.db, keyed on a hash of
the listing content — the date header doesn't count toward that hash, so a
new hour alone won't trigger a repost).

Groups by game, shows the best deal per game plus anything with an open
preorder, and keeps the message short enough to be actually read.
"""

import os
import sqlite3
import logging
import hashlib
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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS digest_state (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    return conn


def deal_pct(price, msrp):
    if not msrp or msrp <= 0:
        return 0
    return round((msrp - price) / msrp * 100)


def build_digest_body(conn):
    """Returns the content lines that actually matter for the digest — i.e.
    everything except the date header, so fingerprint() below doesn't change
    just because an hour passed with nothing new to report."""
    rows = conn.execute("SELECT * FROM listings ORDER BY fetched_at DESC").fetchall()
    if not rows:
        return ["no listings tracked yet. Check the scraper's sources."]

    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game"]].append(dict(r))

    lines = []
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
    return lines


def build_digest(conn) -> str:
    body_lines = build_digest_body(conn)
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    header = [f"📋 **PackWatch Daily Digest — {today}**", ""]
    return "\n".join(header + body_lines)


def fingerprint(conn) -> str:
    """Stable hash of the digest content (excluding the date header) so we
    can tell whether anything actually changed since the last post."""
    body_lines = build_digest_body(conn)
    return hashlib.sha256("\n".join(body_lines).encode("utf-8")).hexdigest()


def get_last_hash(conn):
    row = conn.execute("SELECT value FROM digest_state WHERE key = 'last_hash'").fetchone()
    return row["value"] if row else None


def set_last_hash(conn, value: str):
    conn.execute(
        "INSERT OR REPLACE INTO digest_state (key, value) VALUES ('last_hash', ?)", (value,)
    )
    conn.commit()


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
    current_hash = fingerprint(conn)
    last_hash = get_last_hash(conn)

    if current_hash == last_hash:
        log.info("No changes since last digest — skipping send.")
        conn.close()
        return

    message = build_digest(conn)
    send_discord_digest(message)
    set_last_hash(conn, current_hash)
    conn.close()
    log.info("Digest sent (%d chars)", len(message))


if __name__ == "__main__":
    run()
