from datetime import datetime, timedelta, timezone
import itertools
import random
import yaml
from .config import ROOT
from .safety import digest
from .schema import now

PATTERNS = {
    "pain": "{industry} {workflow} frustrating manual workaround",
    "spending": "{industry} {buyer} {workflow} paid contract budget",
    "reverse_competitor": "{industry} {workflow} software missing expensive alternative",
    "emerging": "{industry} {workflow} changelog deprecated new API",
    "adjacent": "{industry} {workflow} spreadsheet integration automation",
    "speculative": "{industry} {buyer} uncommon {workflow} problem",
    "distribution": "{industry} {buyer} {workflow} community switching",
    "physical": "{industry} equipment compatibility shipping returns problem",
    "counterevidence": "{industry} {workflow} existing solution solved free alternative",
}


def plan(store, limit=4, task=None):
    cfg = yaml.safe_load((ROOT / "configs/research.yaml").read_text())
    existing = store.all("queries")
    rows = []
    if task:
        dims = {
            "industry": "targeted",
            "buyer": "unknown",
            "workflow": task["query"],
            "geography": "unknown",
            "language": "unknown",
        }
        approach = {"challenge": "counterevidence", "competitor": "reverse_competitor"}.get(
            task["kind"], "pain"
        )
        rows.append((task["query"], dims, approach))
    rejected = {i["id"] for i in store.all("opportunities") if "false-positive" in (i.get("labels") or [])}
    false_observations = {
        e["observation_id"] for e in store.all("opportunity_evidence") if e["opportunity_id"] in rejected
    }
    false_queries = {
        (o.get("provenance") or {}).get("query_id")
        for o in store.all("raw_observations")
        if o["id"] in false_observations
    }
    promising = sorted(
        [q for q in existing if q["id"] not in false_queries],
        key=lambda q: (q.get("yield_count") or 0) / max(1, q.get("attempts") or 1),
        reverse=True,
    )
    for q in promising[: int(limit * 0.60)]:
        if not q.get("cache_until") or q["cache_until"] <= now():
            rows.append((q["text"], q["dimensions"], q["approach"]))
    combos = list(
        itertools.product(
            cfg["industries"],
            cfg["buyers"],
            cfg["workflows"],
            cfg["geographies"],
            cfg.get("languages", ["English"]),
        )
    )
    random.Random(now()[:10]).shuffle(combos)
    seen = {q["query_hash"] for q in existing}
    approaches = [
        k for k in PATTERNS if k != "counterevidence" and (k != "physical" or cfg.get("physical_enabled"))
    ]
    for index, (industry, buyer, workflow, geo, language) in enumerate(combos):
        approach = approaches[(len(existing) + index) % len(approaches)]
        if len(rows) >= max(1, limit - 1):
            break
        dims = {
            "industry": industry,
            "buyer": buyer,
            "workflow": workflow,
            "geography": geo,
            "language": language,
        }
        query = PATTERNS[approach].format(**dims) + " " + geo + " " + language
        if digest(query) not in seen:
            rows.append((query, dims, approach))
    if limit > 1 and rows:
        dims = rows[0][1]
        rows.append((PATTERNS["counterevidence"].format(**dims), dims, "counterevidence"))
    result = []
    for query, dims, approach in rows[:limit]:
        old = next((q for q in existing if q["query_hash"] == digest(query)), None)
        values = {
            "id": store.stable_id("query", digest(query)),
            "query_hash": digest(query),
            "text": query,
            "dimensions": dims,
            "approach": approach,
            "attempts": old.get("attempts", 0) if old else 0,
            "yield_count": old.get("yield_count", 0) if old else 0,
        }
        result.append(store.upsert("queries", values, unique=("query_hash",)))
    return result
