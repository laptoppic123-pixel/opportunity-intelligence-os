"""Finite owner-declared allowances. No balance requests or automatic renewals."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def allowance_spec(source):
    cfg = source.get("config") or {}
    spec = cfg.get("allowance")
    if not spec:
        return None
    expected = {"exa": "promotional_usd", "tavily": "free_credits"}.get(source["name"])
    if not expected or spec.get("kind") != expected or spec.get("basis") != "owner_declared":
        raise ValueError("Invalid declared allowance")
    start = datetime.fromisoformat(spec["starts_at"])
    end = datetime.fromisoformat(spec["expires_at"])
    if not start.tzinfo or not end.tzinfo or not start <= datetime.now(timezone.utc) < end:
        raise ValueError("Declared allowance outside its authorized window")
    limit = Decimal(str(spec["limit"]))
    declared = Decimal(str(spec["declared_starting"]))
    if not limit.is_finite() or not declared.is_finite() or not 0 < limit <= declared:
        raise ValueError("Invalid allowance ceiling")
    return spec


def usage_amount(source, rows):
    spec = allowance_spec(source)
    if spec is None:
        return Decimal(0)
    rows = [r for r in rows if r["created_at"] >= spec["starts_at"]]
    if spec["kind"] == "free_credits":
        # All attempts consume one locally reserved basic-search credit, including failures.
        return sum((Decimal(str(r.get("units") or 1)) for r in rows), Decimal(0))
    # Keep the worst-case hold even if the API reports a lower cost. Unknown costs stay held.
    return sum(
        (
            max(Decimal(str(r.get("estimated_cost") or 0)), Decimal(str(r.get("actual_cost") or 0)))
            for r in rows
        ),
        Decimal(0),
    )


def allowance_reason(source, estimate, rows):
    try:
        spec = allowance_spec(source)
        if spec is None:
            return None
        cost = Decimal(str(estimate))
        if not cost.is_finite() or cost < 0:
            return "invalid request estimate"
        if spec["kind"] == "promotional_usd":
            minimum = Decimal(str(source.get("estimated_cost")))
            if not minimum.is_finite() or minimum <= 0 or cost < minimum:
                return "promotional requests require their full worst-case reservation"
            debit = cost
        else:
            if cost != 0:
                return "free-credit search cannot authorize monetary charges"
            debit = Decimal(1)
        if usage_amount(source, rows) + debit > Decimal(str(spec["limit"])):
            return "owner-declared allowance exhausted"
        return None
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return "invalid or expired owner-declared allowance"
