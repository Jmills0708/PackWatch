"""
PackWatch API
-------------
Thin read API over the SQLite database that scraper.py populates. Serves the
frontend dashboard and can back a notifications worker.

Run locally:
    pip install fastapi uvicorn
    uvicorn api:app --reload

Endpoints:
    GET /deals               -> list + filter + sort listings
    GET /deals/{id}          -> single listing
    GET /games               -> distinct game names (for building filter tabs)
    POST /alerts/subscribe   -> register an email/webhook for a saved search
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from signals import buy_signal

DB_PATH = os.environ.get("PACKWATCH_DB", "packwatch.db")

app = FastAPI(title="PackWatch API")

# Lock this down to your actual frontend domain before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class Deal(BaseModel):
    id: int
    game: str
    set_name: str
    product: str
    retailer: str
    price: float
    shipping: float
    msrp: Optional[float]
    url: str
    status: str
    release_date: Optional[str]
    fetched_at: str
    deal_pct: Optional[int] = None
    signal: Optional[str] = None
    signal_reason: Optional[str] = None


class AlertSubscription(BaseModel):
    email: str
    game: Optional[str] = None
    max_price: Optional[float] = None
    keyword: Optional[str] = None


def _row_to_deal(row: sqlite3.Row) -> Deal:
    d = dict(row)
    deal_pct = None
    if d.get("msrp") and d["msrp"] > 0:
        deal_pct = round((d["msrp"] - d["price"]) / d["msrp"] * 100)
    signal, reason = buy_signal(d["price"], d.get("shipping", 0), d.get("msrp"), d["status"])
    return Deal(**d, deal_pct=deal_pct, signal=signal, signal_reason=reason)


@app.get("/deals", response_model=List[Deal])
def list_deals(
    game: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search set/product/retailer"),
    sort: str = Query("deal", pattern="^(deal|price|soonest)$"),
    limit: int = 100,
):
    conn = get_conn()
    clauses, params = [], []
    if game:
        clauses.append("game = ?")
        params.append(game)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        clauses.append("(set_name LIKE ? OR product LIKE ? OR retailer LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM listings {where}", params).fetchall()
    conn.close()

    deals = [_row_to_deal(r) for r in rows]
    if sort == "deal":
        deals.sort(key=lambda d: d.deal_pct or 0, reverse=True)
    elif sort == "price":
        deals.sort(key=lambda d: d.price + d.shipping)
    elif sort == "soonest":
        deals.sort(key=lambda d: d.release_date or "9999-99-99")
    return deals[:limit]


@app.get("/deals/{deal_id}", response_model=Deal)
def get_deal(deal_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (deal_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _row_to_deal(row)


@app.get("/games")
def list_games():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT game FROM listings ORDER BY game").fetchall()
    conn.close()
    return [r["game"] for r in rows]


@app.post("/alerts/subscribe")
def subscribe(sub: AlertSubscription):
    # Wire this up to a table + your email/webhook provider (see DEPLOYMENT.md).
    # Kept as a stub here since it depends on which notification provider you pick.
    return {"status": "received", "subscription": sub, "note": "Persist this and wire to a notifier — see DEPLOYMENT.md"}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
