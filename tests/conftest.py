import httpx
import pytest
from opportunity_intelligence.config import Settings
from opportunity_intelligence.store import Store
from opportunity_intelligence.providers import ProviderRegistry


@pytest.fixture(autouse=True)
def deny_live_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Live network is forbidden in BUILD offline tests")

    monkeypatch.setattr(httpx.Client, "send", denied)
    for key in ["OI_LIVE_ENABLED", "OI_ACTIVATED", "OI_PAID_ENABLED"]:
        monkeypatch.setenv(key, "false")


@pytest.fixture
def store(tmp_path):
    settings = Settings(demo=True, data_dir=tmp_path)
    instance = Store(settings, memory=True)
    ProviderRegistry(instance).sync()
    yield instance
    instance.engine.dispose()
