"""
Exports the listings table to deals.json — lets the free hosting tier
(GitHub Actions + Vercel static site) work with zero backend server.
The dashboard can fetch this file directly from your repo's raw URL or from
whatever static host serves your frontend.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("PACKWATCH_DB", "packwatch.db")
OUT_PATH = os.environ.get("PACKWATCH_JSON_OUT", "deals.json")


def deal_pct(price, msrp):
    if not msrp or msrp <= 0:
        return None
    return round((msrp - price) / msrp * 100)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM listings ORDER BY fetched_at DESC").fetchall()
    conn.close()

    deals = []
    for r in rows:
        d = dict(r)
        d["deal_pct"] = deal_pct(d["price"], d.get("msrp"))
        deals.append(d)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(deals),
        "deals": deals,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {len(deals)} deals to {OUT_PATH}")


if __name__ == "__main__":
    main()
