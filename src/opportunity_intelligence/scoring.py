from .schema import now

WEIGHTS = {
    "severity": 20,
    "spending": 20,
    "recurrence": 15,
    "underserved_gap": 15,
    "distribution": 15,
    "feasibility": 10,
    "momentum": 5,
}
VERSION = "digital-v2.0"


def calculate(dimensions):
    unknown = set(dimensions) - set(WEIGHTS)
    if unknown:
        raise ValueError("Unknown scoring dimension")
    known = {k: v for k, v in dimensions.items() if v is not None}
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 5 for v in known.values()):
        raise ValueError("Assessed scores must be between zero and five")
    coverage = sum(WEIGHTS[k] for k in known)
    score = round(sum(WEIGHTS[k] * v / 5 for k, v in known.items()) * 100 / coverage, 2) if coverage else None
    return {
        "dimensions": {k: dimensions.get(k) for k in WEIGHTS},
        "weighted_score": score,
        "coverage": coverage,
        "version": VERSION,
    }


def save_score(store, opportunity, dimensions, evidence_ids=(), model="rules-only"):
    # Physical candidates are never mixed into the digital score/ranking.
    result = calculate(dimensions if opportunity.get("track") != "physical" else {})
    result.update(
        {
            "opportunity_id": opportunity["id"],
            "model_version": model,
            "evidence_ids": list(evidence_ids),
            "assessed_at": now(),
        }
    )
    old = store.list("scores", opportunity_id=opportunity["id"], limit=1)
    if old and all(
        old[0].get(k) == result.get(k)
        for k in ["dimensions", "weighted_score", "coverage", "version", "model_version", "evidence_ids"]
    ):
        return old[0]
    row = store.upsert("scores", result, unique=("opportunity_id",))
    store.add("score_history", {"opportunity_id": opportunity["id"], "snapshot": result, "event": "scored"})
    return row
