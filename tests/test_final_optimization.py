import json
from pathlib import Path
import pytest
import yaml
from opportunity_intelligence.models import parse_review, validate_evidence, generation_options, SYSTEM


def compact():
    return {
        "solution": "Hypothesis: a focused export check.",
        "mvp": "Check one export.",
        "weaknesses": ["Demand unknown"],
        "unknowns": ["Compare current alternatives"],
        "evidence": [{"source_id": "source-1", "quote": "Manual reconciliation is required."}],
    }


def test_compact_output_preserves_exact_grounding_and_unknown_scores():
    idea = {"id": "idea-1"}
    obs = {"id": "source-1", "excerpt": "Manual reconciliation is required."}
    batch = parse_review(json.dumps(compact()), idea)
    assert validate_evidence(batch, [idea], [obs])
    assert batch.assessments[0].scores == {} and batch.assessments[0].confidence is None
    for source, quote in [("invented", obs["excerpt"]), ("source-1", "made up")]:
        body = compact()
        body["evidence"] = [{"source_id": source, "quote": quote}]
        with pytest.raises(ValueError):
            validate_evidence(parse_review(json.dumps(body), idea), [idea], [obs])
    assert len(SYSTEM) < 1000 and "$defs" not in SYSTEM


def test_generation_limits_follow_advertised_parameters_and_provider_cap():
    model = {
        "id": "fixture:free",
        "supported_parameters": ["max_completion_tokens", "reasoning"],
        "max_completion_tokens": 2048,
        "reasoning": {"mandatory": True, "supported_efforts": ["high", "low"]},
    }
    options, cap = generation_options(model)
    assert options["max_completion_tokens"] == cap == 2048 and "max_tokens" not in options
    assert options["reasoning"]["effort"] == "low" and "enabled" not in options["reasoning"]
    options, _ = generation_options({"id": "fixture", "supported_parameters": []})
    assert not options
    options, cap = generation_options(
        {"id": "openrouter/free", "supported_parameters": ["reasoning", "max_tokens"]}
    )
    assert cap == 3072 and options["max_tokens"] == 3072 and "reasoning" not in options


def test_scheduled_template_has_only_the_approved_cadence():
    root = Path(__file__).resolve().parents[1]
    template = yaml.safe_load(
        (root / ".github/workflows/research-scheduled.yml.disabled").read_text(encoding="utf-8")
    )
    assert [s["cron"] for s in template["on"]["schedule"]] == [
        "17 1,7,13,19 * * *",
        "41 3 * * *",
        "53 4 * * 0",
    ]
    assert template["jobs"]["research"]["env"]["OI_PAID_ENABLED"] == "false"
    active = root / ".github/workflows/research-scheduled.yml"
    if active.exists():
        assert yaml.safe_load(active.read_text(encoding="utf-8")) == template


def test_request_is_one_opportunity_and_only_relevant_short_records(store, monkeypatch):
    from opportunity_intelligence.demo import seed_demo
    from opportunity_intelligence.models import ModelRouter
    from opportunity_intelligence.providers import ProviderRegistry
    from opportunity_intelligence.schema import now

    seed_demo(store)
    ideas = store.all("opportunities")[:2]
    linked = store.list("opportunity_evidence", opportunity_id=ideas[0]["id"])[0]["observation_id"]
    observation = store.get("raw_observations", linked)
    source = store.list("source_registry", name="openrouter")[0]
    store.update(
        "source_registry",
        source["id"],
        {
            "config": {
                **source["config"],
                "catalog_fetched_at": now(),
                "catalog": [
                    {
                        "id": "fixture:free",
                        "prompt": "0",
                        "completion": "0",
                        "supported_parameters": ["max_tokens", "response_format"],
                    }
                ],
            }
        },
    )
    monkeypatch.setenv("FAST_MODEL", "fixture:free")

    class Fixture:
        def __init__(self):
            self.store, self.registry = store, ProviderRegistry(store)

        def request(self, source, *args, **kwargs):
            body = kwargs["payload"]
            records = json.loads(body["messages"][1]["content"])["untrusted_source_records"]
            assert len(records["opportunities"]) == 1 and len(records["records"]) <= 3
            assert all(o["id"] == linked and len(o["excerpt"]) <= 450 for o in records["records"])
            assert (
                len(body["messages"][0]["content"]) < 1000 and "$defs" not in body["messages"][0]["content"]
            )
            wire = compact()
            wire["evidence"] = [{"source_id": linked, "quote": observation["excerpt"][:80]}]
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(wire)}}]}

    result, _ = ModelRouter(Fixture()).analyze(ideas, store.all("raw_observations"))
    assert result and len(result.assessments) == 1 and result.assessments[0].opportunity_id == ideas[0]["id"]
