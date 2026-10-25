"""Deferred AI work uses the existing owner-scoped queue and authorized worker lease."""

from datetime import timedelta
from .ai_reliability import utc, instant, next_day
from .schema import now
from .models import ModelRouter

AI_KINDS = {"ai_fast", "ai_deep", "ai_critic"}


def due_time(store):
    due = utc() + timedelta(minutes=5)
    for source in store.all("source_registry"):
        if source["name"] != "openrouter":
            continue
        cfg = source.get("config") or {}
        state = cfg.get("ai_reliability") or {}
        for value in [cfg.get("blocked_until"), state.get("provider_until")]:
            stamp = instant(value)
            if stamp:
                due = max(due, stamp)
        if state.get("requires_review"):
            due = max(due, utc() + timedelta(days=1))
        model_waits = [instant(v.get("until")) for v in state.get("models", {}).values()]
        model_waits = [stamp for stamp in model_waits if stamp and stamp > utc()]
        if model_waits:
            due = max(due, min(model_waits))
        for q in store.all("source_quotas", source_id=source["id"]):
            if q["used"] < q["limit_value"]:
                continue
            if q["period"] == now()[:10]:
                due = max(due, next_day())
            if q["period"] == now()[:7]:
                month = utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                due = max(due, (month + timedelta(days=32)).replace(day=1))
    return due.isoformat()


def enqueue(store, ideas, *, role="fast", run_id=None):
    if "ai_" + role not in AI_KINDS:
        raise ValueError("Unknown AI queue role")
    due = due_time(store)
    for idea in ideas:
        identifier = store.stable_id("deferred-ai", idea["id"], role)
        existing = store.get("research_queue", identifier)
        if existing and existing["status"] == "cancelled":
            continue
        store.upsert(
            "research_queue",
            {
                "id": identifier,
                "opportunity_id": idea["id"],
                "kind": "ai_" + role,
                "query": "Analyze existing evidence: " + idea["title"],
                "priority": 70 if idea.get("pinned") else 60,
                "status": "pending",
                "due_at": due,
                "run_id": run_id,
                "attempts": (existing or {}).get("attempts") or 0,
                "last_error": "AI deferred; opportunity and source evidence retained",
            },
        )


def resume(transport, *, limit=1):
    """Called only inside an already-authorized bounded worker; creates no scheduler."""
    store = transport.store
    jobs = sorted(
        [
            q
            for q in store.all("research_queue")
            if q.get("kind") in AI_KINDS
            and q["status"] == "pending"
            and (not q.get("due_at") or q["due_at"] <= now())
        ],
        key=lambda q: (-(q.get("priority") or 0), q["created_at"]),
    )
    completed, attempted = 0, set()
    for job in jobs[:limit]:
        if transport.requests >= store.settings.max_requests:
            break
        idea = store.get("opportunities", job["opportunity_id"])
        if not idea:
            continue
        attempted.add(idea["id"])
        # Keep pending with a future due time before any HTTP, so an interrupted worker loses no task.
        store.update("research_queue", job["id"], {"due_at": due_time(store), "run_id": transport.run_id})
        evidence = store.list("opportunity_evidence", opportunity_id=idea["id"])
        identifiers = dict.fromkeys(e["observation_id"] for e in evidence if e.get("observation_id"))
        observations = [store.get("raw_observations", key) for key in list(identifiers)[:12]]
        observations = [o for o in observations if o and not o.get("archived")]
        role = job["kind"].removeprefix("ai_")
        before = transport.requests
        router = ModelRouter(transport)
        batch, identity = router.analyze(
            [idea],
            observations,
            role=role,
            independent_from=idea.get("model_version") if role == "critic" else None,
        )
        if batch:
            router.apply(batch, identity, critique=role == "critic")
            store.update(
                "research_queue",
                job["id"],
                {
                    "status": "completed",
                    "last_error": None,
                    "attempts": (job.get("attempts") or 0) + int(transport.requests > before),
                },
            )
            completed += 1
        else:
            store.update(
                "research_queue",
                job["id"],
                {
                    "status": "pending",
                    "due_at": due_time(store),
                    "attempts": (job.get("attempts") or 0) + int(transport.requests > before),
                    "last_error": "AI deferred; no validated AI assessment applied",
                },
            )
    return completed, attempted
