import httpx
import pytest
from opportunity_intelligence.transport import Transport


def test_unexpected_charge_is_recorded_and_provider_stopped(store, monkeypatch):
    monkeypatch.setattr(store.settings, "require_live", lambda: None)

    class FixtureClient:
        def request(self, *args, **kwargs):
            return httpx.Response(200, json={"usage": {"cost": 0.2, "total_tokens": 5}})

    source = store.list("source_registry", name="hn_algolia")[0]
    transport = Transport(store, client=FixtureClient())
    with pytest.raises(PermissionError):
        transport.request(source, "GET", "https://example.com/fixture", estimate=0, model=True)
    assert store.list("provider_usage")[0]["actual_cost"] == 0.2
    assert store.get("source_registry", source["id"])["failure_count"] == 3
    assert transport.registry.reason(source).startswith("circuit breaker")
