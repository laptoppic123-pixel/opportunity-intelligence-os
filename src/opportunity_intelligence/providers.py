from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import yaml
from .schema import now
from .allowances import allowance_reason, allowance_spec, usage_amount
from .ai_reliability import provider_pause, upgrade_legacy


class ProviderRegistry:
    def __init__(self, store):
        self.store = store
        self.settings = store.settings

    def sync(self):
        specs = yaml.safe_load(self.settings.sources_file.read_text(encoding="utf-8"))["providers"]
        for name, spec in specs.items():
            key_env = spec.get("key_env")
            present = bool(os.getenv(key_env, "")) if key_env else True
            old = self.store.list("source_registry", name=name, limit=1)
            prior = old[0] if old else {}
            config = {
                **spec,
                **{
                    k: v
                    for k, v in (prior.get("config") or {}).items()
                    if k in {"catalog", "catalog_fetched_at", "blocked_until", "ai_reliability"}
                },
            }
            failures = (
                upgrade_legacy(prior, config) if name == "openrouter" else prior.get("failure_count", 0)
            )
            self.store.upsert(
                "source_registry",
                {
                    "id": self.store.stable_id("provider", name),
                    "name": name,
                    "enabled": bool(spec.get("enabled")),
                    "credentials_present": present,
                    "current_terms_checked": bool(spec.get("current_terms_checked")),
                    "capabilities": spec.get("capabilities", []),
                    "estimated_cost": spec.get("estimated_cost"),
                    "daily_quota": spec.get("daily_quota"),
                    "monthly_quota": spec.get("monthly_quota"),
                    "reset_date": spec.get("reset_date"),
                    "failure_count": failures,
                    "last_success": prior.get("last_success"),
                    "last_error": prior.get("last_error"),
                    "added_information_value": prior.get("added_information_value", 0),
                    "priority": spec.get("priority", 100),
                    "legal_access_notes": spec.get("legal_access_notes", ""),
                    "config": config,
                },
                unique=("name",),
            )
        return self.store.all("source_registry")

    def reason(self, source, estimate=None):
        cfg = source.get("config") or {}
        if cfg.get("restricted"):
            return "restricted; legitimate access not configured"
        if not source.get("enabled"):
            return "disabled"
        if not source.get("current_terms_checked"):
            return "current access terms need review"
        if not source.get("credentials_present") and not cfg.get("optional_key"):
            return "missing credential"
        if source["name"] == "openrouter" and provider_pause(source):
            return provider_pause(source)
        if source.get("failure_count", 0) >= 3:
            return "circuit breaker open; owner review/reset required"
        if cfg.get("blocked_until", "") > now():
            return "provider requested backoff"
        cost = source.get("estimated_cost") if estimate is None else estimate
        if cost is None or not Decimal(str(cost)).is_finite() or Decimal(str(cost)) < 0:
            return "unknown request price"
        if cfg.get("allowance"):
            rows = self.store.all("provider_usage", source_id=source["id"])
            return allowance_reason(source, cost, rows)
        if Decimal(str(cost)) > 0:
            if not self.settings.paid:
                return "paid access disabled"
            headroom = cfg.get("credit_headroom")
            checked = cfg.get("credit_checked_at")
            if headroom is None or not checked:
                return "unknown credit headroom"
            try:
                if datetime.fromisoformat(checked) < datetime.now(timezone.utc) - timedelta(hours=24):
                    return "stale credit headroom"
            except (ValueError, TypeError):
                return "invalid credit verification time"
            committed = sum(
                (u["actual_cost"] if u["status"] == "settled" else u["estimated_cost"]) or 0
                for u in self.store.all("provider_usage", source_id=source["id"])
                if u["created_at"] >= checked
            )
            if Decimal(str(headroom)) - Decimal(str(committed)) < Decimal(str(cost)):
                return "insufficient verified credits"
        return None

    def reserve(self, source, *, estimate=None, run_id=None):
        reason = self.reason(source, estimate)
        if reason:
            raise PermissionError(source["name"] + ": " + reason)
        return self.store.reserve(
            source,
            source["estimated_cost"] if estimate is None else estimate,
            run_id=run_id,
            credit_type=(source.get("config") or {}).get("credit_type", "free"),
        )

    def success(self, source):
        source["failure_count"] = 0
        self.store.update(
            "source_registry", source["id"], {"failure_count": 0, "last_success": now(), "last_error": None}
        )

    def failure(self, source, kind):
        current = self.store.get("source_registry", source["id"])
        source["failure_count"] = current.get("failure_count", 0) + 1
        self.store.update(
            "source_registry",
            source["id"],
            {"failure_count": current.get("failure_count", 0) + 1, "last_error": str(kind)[:180]},
        )

    def status(self):
        return [
            {
                **{
                    k: s.get(k)
                    for k in (
                        "name",
                        "enabled",
                        "credentials_present",
                        "capabilities",
                        "daily_quota",
                        "monthly_quota",
                        "estimated_cost",
                        "last_success",
                        "last_error",
                        "failure_count",
                        "priority",
                        "current_terms_checked",
                        "legal_access_notes",
                        "added_information_value",
                        "reset_date",
                    )
                },
                "skip_reason": self.reason(s),
                "declared_allowance": self.allowance_status(s),
            }
            for s in self.store.all("source_registry")
        ]

    def allowance_status(self, source):
        if not source.get("config", {}).get("allowance"):
            return None
        try:
            spec = allowance_spec(source)
            used = usage_amount(source, self.store.all("provider_usage", source_id=source["id"]))
            return {
                "basis": "owner_declared_not_provider_verified",
                "kind": spec["kind"],
                "limit": float(spec["limit"]),
                "reserved_consumption": float(used),
                "remaining_local": float(max(0, Decimal(str(spec["limit"])) - used)),
                "expires_at": spec["expires_at"],
            }
        except (ValueError, KeyError, TypeError):
            return {"status": "invalid_or_expired"}
