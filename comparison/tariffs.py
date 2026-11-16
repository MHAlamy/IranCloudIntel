"""Pure progressive tariff arithmetic; no storage or presentation dependencies."""
from decimal import Decimal

def tier_cost(rates: list[dict], quantity_gb: Decimal) -> tuple[Decimal | None, bool]:
    """Cost of `quantity_gb` under tiered (min_gb, max_gb, amount, is_free) rows.

    Returns (total | None, fully_covered). Tiers are consumed in ascending
    order; unbounded last tiers (max=None) absorb the remainder. None means
    the quantity exceeds every documented bounded tier without an unbounded one.
    """
    if quantity_gb < 0:
        return None, False
    if quantity_gb == 0:
        return Decimal(0), True
    ordered = sorted(rates, key=lambda r: Decimal(r['range_min_gb'] or '0'))
    cursor = Decimal(0)
    total = Decimal(0)
    for row in ordered:
        lo = Decimal(row['range_min_gb'] or '0')
        hi = Decimal(row['range_max_gb']) if row['range_max_gb'] is not None else None
        if cursor is None or lo != cursor or (hi is not None and hi <= lo):
            return None, False
        amount = Decimal(0) if row['is_free'] else (Decimal(row['amount']) if row['amount'] is not None else None)
        if amount is None or amount < 0:
            return None, False
        end = min(quantity_gb, hi) if hi is not None else quantity_gb
        total += max(Decimal(0), end - lo) * amount
        cursor = hi
    return (total, True) if ordered and (cursor is None or cursor >= quantity_gb) else (None, False)


