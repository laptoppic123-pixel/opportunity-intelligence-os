import json
from opportunity_intelligence.models import ModelRouter
from opportunity_intelligence.schema import now
from opportunity_intelligence.demo import seed_demo


def test_model_fallback_rejects_fabricated_sources(store, monkeypatch):
    seed_demo(store)
    idea = store.all("opportunities")[0]
    observation = store.all("raw_observations")[0]
    for name in ["openrouter", "haimaker"]:
        row = store.list("source_registry", name=name)[0]
        store.update(
            "source_registry",
            row["id"],
            {
                "enabled": True,
                "credentials_present": True,
                "current_terms_checked": True,
                "config": {
                    **row["config"],
                    "base_url": "https://example.com/api",
                    "catalog_fetched_at": now(),
                    "catalog": [
                        {"id": "fixture-only-model", "prompt": "0", "completion": "0", "request": "0"}
                    ],
                },
            },
        )
    monkeypatch.setenv("FAST_MODEL", "fixture-only-model")
    monkeypatch.setenv("HAIMAKER_FAST_MODEL", "fixture-only-model")
    calls = []

    class FakeRegistry:
        def failure(self, *args):
            pass

    class FakeTransport:
        registry = FakeRegistry()

        def __init__(self):
            self.store = store

        def request(self, source, *args, **kwargs):
            calls.append(source["name"])
            response = {
                "assessments": [
                    {
                        "opportunity_id": idea["id"],
                        "solution": "Hypothesis",
                        "mvp": "One workflow",
                        "weaknesses": ["Unverified buyer"],
                        "unknowns": ["Demand"],
                        "scores": {},
                        "claims": [
                            {
                                "source_id": "fabricated" if len(calls) == 1 else observation["id"],
                                "claim": observation["excerpt"],
                                "claim_type": "source_fact",
                                "quote": observation["excerpt"],
                            }
                        ],
                    }
                ]
            }
            return {"choices": [{"message": {"content": json.dumps(response)}}]}

    result, identity = ModelRouter(FakeTransport()).analyze([idea], [observation])
    assert calls == ["openrouter", "haimaker"] and result and identity.startswith("haimaker:")


def test_no_model_means_rules_only(store):
    class Fake:
        def __init__(self):
            self.store = store

        def request(self, *args, **kwargs):
            raise AssertionError("No model should be called")

    assert ModelRouter(Fake()).analyze([], []) == (None, None)


def test_free_price_ceiling_and_private_validation_diagnostics(store, monkeypatch):
    seed_demo(store)
    source = store.list("source_registry", name="openrouter")[0]
    store.update(
        "source_registry",
        source["id"],
        {
            "config": {
                **source["config"],
                "catalog_fetched_at": now(),
                "catalog": [{"id": "fixture:free", "prompt": "0", "completion": "0", "request": "0"}],
            }
        },
    )
    monkeypatch.setenv("FAST_MODEL", "fixture:free")
    from opportunity_intelligence.providers import ProviderRegistry

    class FixtureTransport:
        def __init__(self):
            self.store = store
            self.registry = ProviderRegistry(store)

        def request(self, source, *args, **kwargs):
            assert kwargs["payload"]["provider"]["max_price"] == {
                "prompt": 0,
                "completion": 0,
                "request": 0,
            }
            return {"choices": [{"message": {"content": '{"assessments":"PRIVATE_RESPONSE_TEXT"}'}}]}

    assert ModelRouter(FixtureTransport()).analyze(
        store.all("opportunities")[:1], store.all("raw_observations")[:1]
    ) == (None, None)
    error = store.get("source_registry", source["id"])["last_error"]
    assert "list_type" in error and "PRIVATE_RESPONSE_TEXT" not in error


def test_parser_accepts_only_deterministic_json_and_keeps_evidence_strict():
    import pytest
    from opportunity_intelligence.models import parse_result, validate_evidence

    idea = {"id": "opportunity-1"}
    observation = {"id": "source-1", "excerpt": "Exports require manual reconciliation."}
    row = {
        "opportunity_id": idea["id"],
        "solution": "Hypothesis: reconcile exports",
        "mvp": "One format",
        "weaknesses": ["Demand unknown"],
        "unknowns": ["Willingness to pay"],
        "scores": {},
        "claims": [
            {
                "source_id": observation["id"],
                "claim_type": "source_fact",
                "claim": observation["excerpt"],
                "quote": observation["excerpt"],
            }
        ],
    }
    encoded = json.dumps({"assessments": [row]})
    for value in [
        encoded,
        "```json\n" + encoded + "\n```",
        json.dumps([row]),
        [{"type": "text", "text": encoded}],
    ]:
        batch = parse_result(value)
        assert validate_evidence(batch, [idea], [observation])
    for invalid in [
        '{"assessments":[],"assessments":[]}',
        encoded + " extra",
        "Here is JSON: " + encoded,
        "```json\n" + encoded,
        '{"assessments":NaN}',
    ]:
        with pytest.raises(ValueError):
            parse_result(invalid)
    for changed in [
        {"source_id": "invented"},
        {"quote": "made up"},
        {"claim": "false paraphrase"},
        {"claim_type": "hypothesis", "quote": None},
    ]:
        bad = {**row, "claims": [{**row["claims"][0], **changed}]}
        with pytest.raises(ValueError):
            validate_evidence(parse_result(json.dumps({"assessments": [bad]})), [idea], [observation])


def test_json_mode_and_prompt_only_models_use_catalog_capabilities(store, monkeypatch):
    seed_demo(store)
    from opportunity_intelligence.models import parse_result
    from opportunity_intelligence.providers import ProviderRegistry

    source = store.list("source_registry", name="openrouter")[0]
    monkeypatch.setenv("FAST_MODEL", "fixture:free")
    monkeypatch.delenv("FALLBACK_MODEL", raising=False)
    for params in [[], ["response_format"]]:
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
                            "supported_parameters": params,
                        }
                    ],
                }
            },
        )

        class Fixture:
            def __init__(self):
                self.store, self.registry = store, ProviderRegistry(store)

            def request(self, source, *args, **kwargs):
                payload = kwargs["payload"]
                assert (payload.get("response_format") == {"type": "json_object"}) == bool(params)
                assert "JSON structure" in payload["messages"][0]["content"]
                return {"choices": [{"message": {"content": '{"assessments":[]}'}}]}

        assert ModelRouter(Fixture()).analyze(
            store.all("opportunities")[:1], store.all("raw_observations")[:1]
        ) == (None, None)
