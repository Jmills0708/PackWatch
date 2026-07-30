"""
PackWatch notifier
-------------------
Run this right after scraper.py. It looks at listings_history (the append-only
log scraper.py writes on every run), compares each listing's two most recent
observations, and sends an alert when:
  - a listing's status just flipped to "preorder_open" (it wasn't before), or
  - the price just dropped by more than PRICE_DROP_THRESHOLD_PCT.

Ships wired up for a Discord webhook because it's the fastest free option to
set up (Server Settings → Integrations → Webhooks → copy URL). Swap
`send_discord_alert` for an email provider (Resend/Postmark/SendGrid) or a
push service once you have real subscribers — see DEPLOYMENT.md.

Dedup: alerts_sent stores one row per (listing_key, trigger) so the same
event doesn't fire twice.
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone

import requests

from signals import buy_signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("packwatch.notifier")

DB_PATH = os.environ.get("PACKWATCH_DB", "packwatch.db")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
PRICE_DROP_THRESHOLD_PCT = 10  # alert if price falls 10%+ since the last observation


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def already_sent(conn, listing_key: str, trigger: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM alerts_sent WHERE listing_key = ?",
        (f"{listing_key}::{trigger}",),
    ).fetchone()
    return row is not None


def mark_sent(conn, listing_key: str, trigger: str):
    conn.execute(
        "INSERT OR REPLACE INTO alerts_sent (listing_key, sent_at) VALUES (?, ?)",
        (f"{listing_key}::{trigger}", datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def send_discord_alert(message: str):
    if not DISCORD_WEBHOOK_URL:
        log.warning("No DISCORD_WEBHOOK_URL set — logging instead of sending: %s", message)
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except requests.RequestException as exc:
        log.error("Failed to send Discord alert: %s", exc)


def find_changes(conn):
    """Yield (listing_key, trigger, message) for anything worth alerting on."""
    keys = [r["listing_key"] for r in conn.execute("SELECT DISTINCT listing_key FROM listings_history")]

    for key in keys:
        rows = conn.execute(
            "SELECT * FROM listings_history WHERE listing_key = ? ORDER BY fetched_at DESC LIMIT 2",
            (key,),
        ).fetchall()
        if len(rows) < 2:
            continue  # first time we've seen this listing — nothing to compare against

        latest, previous = rows[0], rows[1]
        label = f"{latest['set_name']} ({latest['product']}) @ {latest['retailer']}"

        # Pull current msrp/shipping from the listings table for the buy-signal calc
        current = conn.execute(
            "SELECT msrp, shipping FROM listings WHERE game=? AND set_name=? AND product=? AND retailer=?",
            (latest["game"], latest["set_name"], latest["product"], latest["retailer"]),
        ).fetchone()
        msrp = current["msrp"] if current else None
        shipping = current["shipping"] if current else 0
        signal, reason = buy_signal(latest["price"], shipping, msrp, latest["status"])
        circle = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[signal]

        if latest["status"] == "preorder_open" and previous["status"] != "preorder_open":
            yield key, "preorder_open", f"{circle} Preorder just opened: **{label}** — ${latest['price']:.2f}\n_{reason}_"

        if previous["price"] > 0:
            drop_pct = (previous["price"] - latest["price"]) / previous["price"] * 100
            if drop_pct >= PRICE_DROP_THRESHOLD_PCT:
                yield (
                    key,
                    "price_drop",
                    f"{circle} Price drop: **{label}** — ${previous['price']:.2f} → ${latest['price']:.2f} ({drop_pct:.0f}% off)\n_{reason}_",
                )


def run():
    conn = get_conn()
    sent_count = 0
    for key, trigger, message in find_changes(conn):
        if already_sent(conn, key, trigger):
            continue
        send_discord_alert(message)
        mark_sent(conn, key, trigger)
        sent_count += 1
    log.info("Notifier sent %d new alert(s)", sent_count)
    conn.close()


if __name__ == "__main__":
    run()
