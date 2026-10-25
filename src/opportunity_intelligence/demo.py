from .providers import ProviderRegistry
from .sources import Observation
from .intelligence import ingest, rules_analysis
from .services import edit_idea, add_note, queue_research
from .scoring import save_score
from .schema import now

FIXTURES = [
    (
        "accounting",
        "finance manager",
        "data reconciliation",
        "Synthetic: reconciling client invoices across spreadsheets",
        "DEMO ONLY: our fictional finance manager manually reconciles three exports each week.",
        "pain",
    ),
    (
        "logistics",
        "operations manager",
        "tool integration",
        "Synthetic: shipment status does not reach the customer portal",
        "DEMO ONLY: a fictional small logistics team copies status changes between disconnected tools.",
        "adjacent",
    ),
    (
        "education",
        "owner",
        "client onboarding",
        "Synthetic: regional-language onboarding gap",
        "DEMO ONLY: a fictional training center wants a simpler bilingual onboarding flow.",
        "speculative",
    ),
    (
        "professional services",
        "independent consultant",
        "reporting",
        "Synthetic: service project asks for report automation",
        "DEMO ONLY: this invented project brief is an illustration, not evidence of actual spending.",
        "spending",
    ),
    (
        "healthcare administration",
        "operations manager",
        "reporting",
        "Synthetic: vendor API change creates reporting work",
        "DEMO ONLY: a fictional vendor changelog requires a new export mapping.",
        "emerging",
    ),
    (
        "logistics",
        "owner",
        "equipment compatibility",
        "Synthetic physical track: scanner compatibility",
        "DEMO ONLY: hypothetical hardware compatibility issue; shipping and return economics are unknown.",
        "physical",
    ),
]


def seed_demo(store):
    if not store.settings.demo:
        raise PermissionError("Synthetic seed is restricted to explicit demo mode")
    registry = ProviderRegistry(store)
    registry.sync()
    if store.list("raw_observations", synthetic=True, limit=1):
        return
    source = store.list("source_registry", name="hn_algolia", limit=1)[0]
    for i, (industry, buyer, workflow, title, excerpt, approach) in enumerate(FIXTURES):
        query = {
            "id": None,
            "dimensions": {
                "industry": industry,
                "buyer": buyer,
                "workflow": workflow,
                "geography": "Synthetic global example",
                "language": "English",
            },
            "approach": approach,
        }
        ingest(
            store,
            source,
            Observation(
                f"synthetic-{i}",
                f"https://example.com/synthetic/opportunity-{i}",
                title,
                excerpt,
                now(),
                f"synthetic-author-{i}",
                "SYNTHETIC fixture; no real source or buyer",
            ),
            query=query,
            synthetic=True,
        )
    ideas = rules_analysis(store)
    for i, idea in enumerate(ideas):
        save_score(
            store,
            idea,
            {"severity": 3 if i % 2 == 0 else None, "feasibility": 4 if i < 3 else None},
            [],
            "synthetic illustration",
        )
        store.update(
            "opportunities",
            idea["id"],
            {"effort": 2 if i < 3 else None, "status": "emerging" if i == 4 else "speculative"},
        )
    edit_idea(store, ideas[0]["id"], favorite=True, labels=["SYNTHETIC", "demo"])
    add_note(store, ideas[0]["id"], "SYNTHETIC owner note: ask a real buyer before treating this as demand.")
    queue_research(
        store, "SYNTHETIC task: investigate reconciliation workflow", opportunity_id=ideas[0]["id"]
    )
