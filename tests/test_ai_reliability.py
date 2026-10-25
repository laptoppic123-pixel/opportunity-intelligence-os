import json
from datetime import timedelta
from email.utils import format_datetime
import httpx
import pytest
from opportunity_intelligence.ai_reliability import FREE_ROUTER, utc, next_day, instant
from opportunity_intelligence.ai_queue import enqueue, resume
from opportunity_intelligence.demo import seed_demo
from opportunity_intelligence.models import ModelRouter, parse_result
from opportunity_intelligence.providers import ProviderRegistry
from opportunity_intelligence.schema import now
from opportunity_intelligence.transport import Transport

PREFERRED = "fixture/preferred:free"
RESOLVED = "fixture/resolved:free"


@pytest.fixture
def scenario(store, monkeypatch):
    seed_demo(store)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-only-key")
    monkeypatch.setenv("FAST_MODEL", PREFERRED)
    monkeypatch.setenv("CRITIC_MODEL", PREFERRED)
    monkeypatch.setenv("FALLBACK_MODEL", "")
    monkeypatch.setattr(store.settings, "require_live", lambda: None)
    source = store.list("source_registry", name="openrouter")[0]
    source = store.update(
        "source_registry",
        source["id"],
        {
            "enabled": True,
            "credentials_present": True,
            "current_terms_checked": True,
            "failure_count": 0,
            "config": {
                **source["config"],
                "free_router_enabled": True,
                "ai_reliability": {"version": 1, "models": {}},
                "catalog_fetched_at": now(),
                "catalog": [
                    {
                        "id": key,
                        "prompt": "0",
                        "completion": "0",
                        "request": "0",
                        "supported_parameters": ["response_format"],
                    }
                    for key in [PREFERRED, FREE_ROUTER, RESOLVED]
                ],
            },
        },
    )
    idea, obs = store.all("opportunities")[0], store.all("raw_observations")[0]
    payload = {
        "assessments": [
            {
                "opportunity_id": idea["id"],
                "solution": "Hypothesis: reduce manual work",
                "mvp": "One workflow",
                "weaknesses": ["Demand unknown"],
                "unknowns": ["Alternatives unknown"],
                "scores": {},
                "claims": [
                    {
                        "source_id": obs["id"],
                        "claim_type": "source_fact",
                        "claim": obs["excerpt"],
                        "quote": obs["excerpt"],
                    }
                ],
            }
        ]
    }
    return source, idea, obs, payload


class Client:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []

    def request(self, method, url, **kwargs):
        assert kwargs["json"]["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        self.calls.append(kwargs["json"]["model"])
        return next(self.responses)


def success(payload, model=RESOLVED):
    return httpx.Response(
        200,
        json={
            "model": model,
            "usage": {"cost": 0},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
        },
    )


@pytest.mark.parametrize("status", [404, 429])
def test_preferred_unavailable_falls_back_once_to_zero_price_router(store, scenario, status):
    source, idea, obs, payload = scenario
    client = Client(
        [
            httpx.Response(
                status,
                json={
                    "error": {
                        "message": "temporarily rate-limited upstream",
                        "metadata": {"provider_name": "Fixture"},
                    }
                },
            ),
            success(payload),
        ]
    )
    t = Transport(store, client=client)
    router = ModelRouter(t)
    result, identity = router.analyze([idea], [obs])
    assert result and identity == "openrouter:" + RESOLVED
    assert client.calls == [PREFERRED, FREE_ROUTER]
    router.apply(result, identity)
    current = store.get("opportunities", idea["id"])
    assert current["analysis_method"] == "llm-assisted" and not current["customer_validated"]


def test_healthy_preferred_does_not_use_router(store, scenario):
    _, idea, obs, payload = scenario
    client = Client([success(payload, PREFERRED)])
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs])[0]
    assert client.calls == [PREFERRED]


def test_exhausted_daily_allowance_suspends_all_models_and_persists(store, scenario):
    source, idea, obs, _ = scenario
    client = Client([httpx.Response(429, json={"error": {"message": "free-models-per-day exhausted"}})])
    router = ModelRouter(Transport(store, client=client))
    assert router.analyze([idea], [obs]) == (None, None)
    ProviderRegistry(store).sync()
    assert router.analyze([idea], [obs]) == (None, None)
    assert client.calls == [PREFERRED]
    current = store.get("source_registry", source["id"])
    assert instant(current["config"]["ai_reliability"]["provider_until"]) >= next_day()
    enqueue(store, [idea])
    enqueue(store, [idea])
    jobs = store.list("research_queue", kind="ai_fast")
    assert len(jobs) == 1 and instant(jobs[0]["due_at"]) >= next_day()


@pytest.mark.parametrize("date_header", [False, True])
def test_retry_after_is_not_bypassed_by_router(store, scenario, date_header):
    source, idea, obs, _ = scenario
    future = utc() + timedelta(minutes=30)
    header = format_datetime(future, usegmt=True) if date_header else "1800"
    client = Client(
        [
            httpx.Response(
                429,
                headers={"Retry-After": header},
                json={"error": {"message": "limited upstream", "metadata": {"provider_name": "Fixture"}}},
            )
        ]
    )
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs]) == (None, None)
    pause = store.get("source_registry", source["id"])["config"]["ai_reliability"]
    assert instant(pause["provider_until"]) >= future - timedelta(seconds=2)
    assert client.calls == [PREFERRED]


def test_deferred_work_resumes_on_a_later_authorized_worker(store, scenario, monkeypatch):
    source, idea, obs, payload = scenario
    client = Client([httpx.Response(404), httpx.Response(503)])
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs]) == (None, None)
    enqueue(store, [idea])
    job = store.list("research_queue", kind="ai_fast")[0]
    assert store.get("opportunities", idea["id"])["analysis_method"] == "rules-only"
    # Time passes; no manual circuit reset or queue edit is required.
    from opportunity_intelligence import ai_reliability, ai_queue

    future = utc() + timedelta(minutes=20)
    monkeypatch.setattr(ai_reliability, "utc", lambda: future)
    monkeypatch.setattr(ai_queue, "utc", lambda: future)
    monkeypatch.setattr(ai_queue, "now", lambda: future.isoformat())
    t = Transport(store, client=Client([success(payload, PREFERRED)]))
    completed, attempted = resume(t)
    assert completed == 1 and idea["id"] in attempted and t.requests == 1
    assert store.get("research_queue", job["id"])["status"] == "completed"
    assert store.get("opportunities", idea["id"])["analysis_method"] == "llm-assisted"


@pytest.mark.parametrize("bad", ["source", "quote", "paid_identity", "same_critic"])
def test_router_cannot_bypass_evidence_price_or_critic_independence(store, scenario, bad):
    _, idea, obs, payload = scenario
    if bad == "source":
        payload["assessments"][0]["claims"][0]["source_id"] = "invented"
    if bad == "quote":
        payload["assessments"][0]["claims"][0]["quote"] = "fabricated quotation"
    model = "paid/not-in-free-catalog" if bad == "paid_identity" else RESOLVED
    client = Client([httpx.Response(404), success(payload, model)])
    router = ModelRouter(Transport(store, client=client))
    result = router.analyze(
        [idea],
        [obs],
        role="critic" if bad == "same_critic" else "fast",
        independent_from="openrouter:" + RESOLVED if bad == "same_critic" else None,
    )
    assert result == (None, None)
    assert store.get("opportunities", idea["id"])["analysis_method"] == "rules-only"
    assert not store.get("opportunities", idea["id"])["customer_validated"]


def test_apply_revalidates_before_changing_any_ai_label(store, scenario):
    _, idea, _, payload = scenario
    payload["assessments"][0]["claims"][0]["source_id"] = "invented"
    with pytest.raises(ValueError):
        ModelRouter(Transport(store, client=Client([]))).apply(
            parse_result(json.dumps(payload)), "openrouter:" + RESOLVED
        )
    assert store.get("opportunities", idea["id"])["analysis_method"] == "rules-only"


def test_incomplete_router_output_is_queued_without_an_ai_label(store, scenario):
    _, idea, obs, payload = scenario
    truncated = success(payload).json()
    truncated["choices"][0]["finish_reason"] = "length"
    client = Client([httpx.Response(404), httpx.Response(200, json=truncated)])
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs]) == (None, None)
    enqueue(store, [idea])
    assert store.get("opportunities", idea["id"])["analysis_method"] == "rules-only"
    assert store.list("research_queue", opportunity_id=idea["id"], kind="ai_fast")[0]["status"] == "pending"


def test_http_200_error_envelope_cannot_bypass_daily_suspension(store, scenario):
    source, idea, obs, _ = scenario
    client = Client(
        [httpx.Response(200, json={"error": {"code": 429, "message": "free-models-per-day exhausted"}})]
    )
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs]) == (None, None)
    assert client.calls == [PREFERRED]
    state = store.get("source_registry", source["id"])["config"]["ai_reliability"]
    assert state["reason"] == "free_daily_allowance_exhausted"


def test_error_response_cost_anomaly_cannot_trigger_another_model(store, scenario):
    source, idea, obs, _ = scenario
    client = Client(
        [httpx.Response(429, json={"error": {"message": "upstream limited"}, "usage": {"cost": 0.1}})]
    )
    assert ModelRouter(Transport(store, client=client)).analyze([idea], [obs]) == (None, None)
    assert client.calls == [PREFERRED]
    current = store.get("source_registry", source["id"])
    assert current["config"]["ai_reliability"]["requires_review"]
    assert store.list("provider_usage", source_id=source["id"])[0]["actual_cost"] == 0.1


@pytest.mark.parametrize("status", [200, 429])
def test_catalog_error_never_erases_good_catalog_or_retries_limits(store, scenario, status):
    from opportunity_intelligence.ai_reliability import AIDeferred

    source, idea, obs, _ = scenario

    class CatalogClient:
        calls = 0

        def request(self, *args, **kwargs):
            self.calls += 1
            return httpx.Response(
                status, json={"error": {"code": 429, "message": "free-models-per-day exhausted"}}
            )

    client = CatalogClient()
    router = ModelRouter(Transport(store, client=client))
    with pytest.raises(AIDeferred):
        router.refresh_catalog(source)
    assert router.analyze([idea], [obs]) == (None, None)
    assert client.calls == 1
    assert len(store.get("source_registry", source["id"])["config"]["catalog"]) == 3


def test_research_collection_continues_with_ai_paused(store, scenario, monkeypatch):
    from opportunity_intelligence import orchestrator
    from opportunity_intelligence.sources import Observation

    source = store.get("source_registry", scenario[0]["id"])
    cfg = source["config"]
    cfg["ai_reliability"] = {
        "version": 1,
        "models": {},
        "provider_until": next_day().isoformat(),
        "reason": "free_daily_allowance_exhausted",
    }
    store.update("source_registry", source["id"], {"config": cfg})
    store.settings.demo = (
        False  # Existing in-memory repository, production worker branch; network remains denied.
    )
    query = store.add(
        "queries",
        {
            "query_hash": "reliability-fixture",
            "text": "export reconciliation",
            "dimensions": {},
            "approach": "pain",
        },
    )
    monkeypatch.setattr(orchestrator, "plan", lambda *args, **kwargs: [query])

    def collect(self, source, *args, **kwargs):
        if source["name"] != "hn_algolia":
            return []
        return [
            Observation(
                "reliability-fixture",
                "https://example.com/reliability-fixture",
                "Manual export inconsistency",
                "Exports need a manual consistency check.",
            )
        ]

    monkeypatch.setattr(orchestrator.SourceAdapters, "fetch", collect)
    result = orchestrator.run(store, "discover", live=True)
    assert result["status"] == "completed" and result["new_observations"] == 1
    obs = store.list("raw_observations", source_item_id="reliability-fixture")[0]
    link = store.list("opportunity_evidence", observation_id=obs["id"])[0]
    idea = store.get("opportunities", link["opportunity_id"])
    assert idea["analysis_method"] == "rules-only"
    assert store.list("research_queue", opportunity_id=idea["id"], kind="ai_fast")[0]["status"] == "pending"
