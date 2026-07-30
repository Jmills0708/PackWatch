"""
PackWatch buy signal
----------------------
Turns a listing's price/status data into a green/yellow/red "should I buy
this" signal. Used by digest.py, notifier.py, and api.py so the signal means
the same thing everywhere (and in the dashboard, which reimplements this
same logic in JS — see packwatch_dashboard.jsx's buySignal() function; keep
the two in sync if you change the thresholds here).

Rules (in priority order):
  RED    - price is at/above MSRP (no real discount), or it's "low_stock"
           with a weak discount (classic sign of scalped/inflated pricing)
  YELLOW - no MSRP on record (can't verify it's actually a deal), or a real
           but modest discount (0-10% under MSRP), or preorder hasn't
           opened yet (nothing to lock in a price on yet)
  GREEN  - confirmed 10%+ under MSRP AND status is preorder_open or in_stock
           (a real, actionable discount you can buy right now)
"""

from typing import Optional, Tuple

GREEN_THRESHOLD_PCT = 10  # must beat MSRP by at least this much for "green"


def deal_pct(price: float, shipping: float, msrp: Optional[float]) -> Optional[float]:
    if not msrp or msrp <= 0:
        return None
    effective_price = price + (shipping or 0)
    return (msrp - effective_price) / msrp * 100


def buy_signal(price: float, shipping: float, msrp: Optional[float], status: str) -> Tuple[str, str]:
    """Returns (signal, reason) where signal is 'green' | 'yellow' | 'red'."""
    pct = deal_pct(price, shipping, msrp)

    if pct is None:
        return "yellow", "No MSRP on record — can't confirm this is actually a discount."

    if pct < 0:
        return "red", f"Priced {abs(pct):.0f}% ABOVE MSRP — likely marked up or scalped."

    if status == "low_stock" and pct < GREEN_THRESHOLD_PCT:
        return "red", "Low stock and not a strong discount — risk of paying near/above MSRP if it sells through at this price."

    if pct >= GREEN_THRESHOLD_PCT and status in ("preorder_open", "in_stock"):
        return "green", f"{pct:.0f}% under MSRP and available to buy now."

    if status == "preorder_soon":
        return "yellow", "Preorder hasn't opened yet — price could still change once it does."

    return "yellow", f"Only {pct:.0f}% under MSRP — modest discount, worth a quick price-check elsewhere first."


if __name__ == "__main__":
    tests = [
        (104.99, 0, 119.76, "preorder_open"),   # ~12% off, open -> green
        (89.99, 0, 79.99, "in_stock"),           # over MSRP -> red
        (75.00, 0, 79.99, "in_stock"),           # ~6% off -> yellow
        (78.00, 0, 79.99, "low_stock"),          # weak discount + low stock -> red
        (50.00, 0, None, "in_stock"),            # no msrp -> yellow
        (60.00, 0, 79.99, "preorder_soon"),      # good discount but not open yet -> yellow
    ]
    for price, shipping, msrp, status in tests:
        signal, reason = buy_signal(price, shipping, msrp, status)
        print(f"{signal.upper():6s} | {reason}")
