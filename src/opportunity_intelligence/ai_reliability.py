"""Persist bounded OpenRouter deferrals; never poll balances or log response bodies."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re

FREE_ROUTER = "openrouter/free"


class AIDeferred(PermissionError):
    def __init__(self, reason, until, *, provider_wide=False, status=None):
        super().__init__(reason)
        self.until = until
        self.provider_wide = provider_wide
        self.status = status


def utc():
    return datetime.now(timezone.utc)


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def next_day():
    return (utc() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def retry_after(value):
    if not value:
        return None
    try:
        seconds = float(value)
        if seconds < 0:
            return None
        if seconds > 315360000:
            return datetime.max.replace(tzinfo=timezone.utc)
        return utc() + timedelta(seconds=seconds)
    except (ValueError, TypeError, OverflowError):
        try:
            parsed = parsedate_to_datetime(value)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
        except (ValueError, TypeError, OverflowError):
            return None


def upgrade_legacy(prior, config):
    """Only old, explicitly transient HTTP circuits are eligible for timed recovery."""
    if prior.get("failure_count", 0) >= 3 and not config.get("ai_reliability"):
        if re.search(r"HTTP (429|404|502|503|504)", prior.get("last_error") or ""):
            stamp = instant(prior.get("updated_at")) or utc()
            config["ai_reliability"] = {
                "version": 1,
                "provider_until": (stamp + timedelta(minutes=15)).isoformat(),
                "reason": "legacy_transient_cooldown",
                "models": {},
            }
            return 0
    return prior.get("failure_count", 0)


def provider_pause(source):
    state = source.get("config", {}).get("ai_reliability") or {}
    if state.get("requires_review"):
        return "OpenRouter suspended pending credential/access/cost review"
    until = instant(state.get("provider_until"))
    if until and until > utc():
        return "OpenRouter deferred: " + state.get("reason", "cooldown")
    return None


def model_paused(source, model_id):
    state = source.get("config", {}).get("ai_reliability") or {}
    until = instant((state.get("models", {}).get(model_id) or {}).get("until"))
    return bool(until and until > utc())


def defer(store, source, model_id, reason, *, until=None, provider_wide=False, review=False, status=None):
    until = until or utc() + timedelta(minutes=5)
    cfg = deepcopy(source.get("config") or {})
    state = cfg.setdefault("ai_reliability", {"version": 1, "models": {}})
    state["version"] = 1
    state.setdefault("models", {})
    if provider_wide:
        previous = instant(state.get("provider_until"))
        until = max(until, previous) if previous else until
        state.update(provider_until=until.isoformat(), reason=reason)
        if review:
            state["requires_review"] = True
    else:
        previous = instant((state["models"].get(model_id) or {}).get("until"))
        until = max(until, previous) if previous else until
        state["models"][model_id] = {"until": until.isoformat(), "reason": reason}
    source["config"] = cfg
    source["failure_count"] = 0 if not review else 3
    store.update(
        "source_registry",
        source["id"],
        {
            "config": cfg,
            "failure_count": source["failure_count"],
            "last_error": reason,
        },
    )
    return AIDeferred(reason, until.isoformat(), provider_wide=provider_wide, status=status)


def response_deferral(store, source, model_id, response):
    try:
        error = response.json().get("error") or {}
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {}
    metadata = error.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    message = str(error.get("message", "")).lower()
    status = response.status_code
    if status < 300:
        try:
            code = int(error.get("code", 503))
            status = code if 400 <= code <= 599 else 503
        except (TypeError, ValueError):
            status = 503
    header_value = response.headers.get("Retry-After")
    header_until = retry_after(header_value)
    if header_value and header_until is None:
        header_until = utc() + timedelta(hours=1)
    reset = instant(metadata.get("resets_at"))
    # Read only normal error headers/metadata. Never query /key, /credits or /usage.
    try:
        reset_number = float(response.headers.get("X-RateLimit-Reset", 0))
        if reset_number > 1e11:
            reset_number /= 1000
        if reset_number:
            reset = max(reset or utc(), datetime.fromtimestamp(reset_number, timezone.utc))
    except (ValueError, OverflowError, OSError):
        pass
    daily = any(x in message for x in ("free-models-per-day", "daily limit", "daily free", "free daily"))
    limit_metadata = str(metadata.get("limit_source", "")) + " " + str(metadata.get("reason", ""))
    daily = daily or bool(re.search(r"free.*(daily|per_day)|daily.*free", limit_metadata.lower()))
    if status == 429 and daily:
        until = max(next_day(), header_until or utc(), reset or utc())
        return defer(
            store,
            source,
            model_id,
            "free_daily_allowance_exhausted",
            until=until,
            provider_wide=True,
            status=status,
        )
    if header_until and header_until > utc():
        # A router can reselect the same backend, so never bypass an explicit Retry-After.
        return defer(
            store,
            source,
            model_id,
            "retry_after",
            until=max(header_until, reset or utc()),
            provider_wide=True,
            status=status,
        )
    if status in {401, 402, 403}:
        return defer(
            store,
            source,
            model_id,
            "credential_access_or_credit_suspended",
            until=reset or next_day(),
            provider_wide=True,
            review=not bool(reset),
            status=status,
        )
    if status == 429:
        upstream = bool(metadata.get("provider_name") or "upstream" in message)
        wide = (
            not upstream
            or model_id in {FREE_ROUTER, "catalog"}
            or response.headers.get("X-RateLimit-Remaining") == "0"
        )
        return defer(
            store,
            source,
            model_id,
            "free_rate_limited",
            until=reset or utc() + timedelta(minutes=5),
            provider_wide=wide,
            status=status,
        )
    return defer(
        store,
        source,
        model_id,
        "free_endpoint_unavailable",
        until=utc() + timedelta(minutes=15),
        provider_wide=model_id in {FREE_ROUTER, "catalog"},
        status=status,
    )
