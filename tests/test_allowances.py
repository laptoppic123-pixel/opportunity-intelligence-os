from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from opportunity_intelligence.providers import ProviderRegistry
from opportunity_intelligence.transport import Transport
from opportunity_intelligence.allowances import usage_amount


def declared(store, name, limit):
    source = store.list("source_registry", name=name)[0]
    clock = datetime.now(timezone.utc)
    exa = name == "exa"
    return store.update(
        "source_registry",
        source["id"],
        {
            "enabled": True,
            "current_terms_checked": True,
            "credentials_present": True,
            "failure_count": 0,
            "estimated_cost": 0.02 if exa else 0,
            "config": {
                **source["config"],
                "credit_type": "promotional" if exa else "owner_free_allowance",
                "allowance": {
                    "basis": "owner_declared",
                    "kind": "promotional_usd" if exa else "free_credits",
                    "starts_at": (clock - timedelta(minutes=1)).isoformat(),
                    "expires_at": (clock + timedelta(days=1)).isoformat(),
                    "declared_starting": limit,
                    "limit": limit,
                    "auto_renew": False,
                },
            },
        },
    )


@pytest.mark.parametrize("name,limit", [("exa", 0.02), ("tavily", 1)])
def test_declared_credits_reserve_atomically_and_never_reset_on_settlement(store, name, limit):
    source = declared(store, name, limit)
    registry = ProviderRegistry(store)
    assert registry.reason(source) is None and not store.settings.paid

    def reserve():
        try:
            return store.reserve(
                source, source["estimated_cost"], credit_type=source["config"]["credit_type"]
            )
        except PermissionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = [i for i in pool.map(lambda _: reserve(), range(2)) if i]
    assert len(identifiers) == 1
    store.settle(identifiers[0], 0.007 if name == "exa" else 0)
    assert registry.reason(source) == "owner-declared allowance exhausted"
    assert float(usage_amount(source, store.all("provider_usage"))) == limit
    with pytest.raises(PermissionError):
        store.reserve(source, source["estimated_cost"], credit_type=source["config"]["credit_type"])
    if name == "exa":
        assert "full worst-case" in registry.reason(source, estimate=0)


def test_promo_error_retains_hold_and_stops_402_without_retry(store, monkeypatch):
    source = declared(store, "exa", 0.10)
    monkeypatch.setattr(store.settings, "require_live", lambda: None)

    class Fixture:
        calls = 0

        def request(self, *args, **kwargs):
            self.calls += 1
            return httpx.Response(402, json={"error": "credit exhausted"})

    client = Fixture()
    with pytest.raises(PermissionError):
        Transport(store, client=client).request(source, "POST", "https://api.exa.ai/search")
    assert client.calls == 1
    assert store.all("provider_usage")[0]["status"] == "unknown_charge"
    assert float(usage_amount(source, store.all("provider_usage"))) == 0.02
    assert store.get("source_registry", source["id"])["failure_count"] == 3


def test_allowance_expiry_and_other_provider_cannot_bypass_paid_gate(store):
    source = declared(store, "exa", 1)
    source["config"]["allowance"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    assert "expired" in ProviderRegistry(store).reason(source)
    source["name"] = "serper"
    assert "invalid" in ProviderRegistry(store).reason(source)
