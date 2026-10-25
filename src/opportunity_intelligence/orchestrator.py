from datetime import datetime, timedelta, timezone
import time
import json
import os
from .schema import now
from .providers import ProviderRegistry
from .transport import Transport
from .sources import SourceAdapters
from .planner import plan
from .intelligence import ingest, rules_analysis, enrich, challenge
from .models import ModelRouter
from .ai_queue import enqueue as enqueue_ai, resume as resume_ai, AI_KINDS


def retain(store):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=store.settings.retention_days)).isoformat()
    count = 0
    protected = {i["id"] for i in store.all("opportunities") if i.get("favorite") or i.get("pinned")}
    links = store.all("opportunity_evidence")
    for row in store.all("raw_observations"):
        if row["observed_at"] < cutoff and not row.get("archived"):
            evidence = [e for e in links if e.get("observation_id") == row["id"]]
            if any(e["opportunity_id"] in protected for e in evidence):
                continue
            store.update("raw_observations", row["id"], {"excerpt": None, "archived": True})
            for e in evidence:
                store.update("opportunity_evidence", e["id"], {"quote": None})
            count += 1
    return count


def run(store, command="discover", *, live=False):
    if live:
        store.settings.require_live()
    if not store.settings.demo and not live:
        raise PermissionError("Production worker requires an explicit --live authorization.")
    with store.lease():
        registry = ProviderRegistry(store)
        registry.sync()
        execution = store.add(
            "research_runs",
            {
                "command": command,
                "status": "running",
                "started_at": now(),
                "requests": 0,
                "observations": 0,
                "diagnostics": [],
                "checkpoint": {},
            },
        )
        t = Transport(store, run_id=execution["id"])
        diagnostics = []
        collected = []
        start = time.monotonic()
        try:
            resumed, attempted_ai = (0, set())
            if live and command in {"discover", "analyze", "deep-dive"}:
                resumed, attempted_ai = resume_ai(t, limit=1)
                if resumed:
                    diagnostics.append({"resumed_ai_assessments": resumed})
            if command in {"discover", "deep-dive"} and not store.settings.demo:
                tasks = sorted(
                    [
                        q
                        for q in store.all("research_queue")
                        if q["status"] == "pending"
                        and q.get("kind") not in AI_KINDS
                        and (not q.get("due_at") or q["due_at"] <= now())
                    ],
                    key=lambda q: -(q.get("priority") or 0),
                )
                task = tasks[0] if tasks else None
                if task:
                    store.update(
                        "research_queue",
                        task["id"],
                        {
                            "status": "running",
                            "run_id": execution["id"],
                            "attempts": (task.get("attempts") or 0) + 1,
                        },
                    )
                queries = plan(store, limit=4, task=task)
                sources = sorted(
                    [s for s in store.all("source_registry") if s["config"].get("kind") == "search"],
                    key=lambda s: s.get("priority") or 100,
                )
                adapters = SourceAdapters(t)
                # Leave room for catalog validation and one AI request/fallback in this same bounded job.
                available_ai = any(
                    not registry.reason(s, estimate=0)
                    for s in store.all("source_registry")
                    if s.get("config", {}).get("kind") == "model"
                )
                model_reserve = (
                    2 if available_ai and os.getenv("FAST_MODEL") and os.getenv("OPENROUTER_API_KEY") else 0
                )
                research_cap = max(0, store.settings.max_requests - model_reserve)
                for query in queries:
                    if time.monotonic() - start > store.settings.max_seconds or t.requests >= research_cap:
                        break
                    if query.get("cache_until") and query["cache_until"] > now():
                        continue
                    try:
                        cursors = json.loads(query.get("cursor") or "{}")
                    except (ValueError, TypeError):
                        cursors = {}
                    boundary = now()
                    new = 0
                    successes = 0
                    for source in sources:
                        if registry.reason(source):
                            continue
                        if t.requests >= research_cap or len(collected) >= store.settings.max_documents:
                            break
                        worst_calls = (
                            4 if source["name"] == "hn_official" else (2 if source["name"] == "rss" else 1)
                        )
                        if t.requests + worst_calls > research_cap:
                            continue
                        try:
                            state = cursors.get(source["name"]) or {}
                            if isinstance(state, str):
                                state = {"since": state}
                            since = (
                                state.get("since")
                                or (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                            )
                            page = state.get("page", 0)
                            page_limit = min(5, store.settings.max_documents - len(collected))
                            items = adapters.fetch(
                                source, query["text"], since=since, limit=page_limit, page=page
                            )
                            accepted = 0
                            for item in items:
                                try:
                                    row = ingest(store, source, item, query=query, run_id=execution["id"])
                                except ValueError:
                                    continue
                                if row:
                                    collected.append(row)
                                    new += 1
                                    accepted += 1
                            successes += 1
                            paginated = source["name"] in {"hn_algolia", "github", "stackexchange"}
                            if paginated and len(items) >= page_limit and page < 19:
                                cursors[source["name"]] = {
                                    "since": since,
                                    "page": page + 1,
                                    "until": state.get("until", boundary),
                                }
                            else:
                                cursors[source["name"]] = {"since": state.get("until", boundary), "page": 0}
                                if len(items) >= page_limit:
                                    diagnostics.append(
                                        {
                                            "source": source["name"],
                                            "coverage": "bounded top results; retrieval may be partial",
                                        }
                                    )
                            registry.success(source)
                            store.update(
                                "source_registry",
                                source["id"],
                                {
                                    "added_information_value": source.get("added_information_value", 0)
                                    + accepted
                                },
                            )
                        except (PermissionError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                            diagnostics.append({"source": source["name"], "error": type(exc).__name__})
                            registry.failure(source, type(exc).__name__)
                    # Only advance the persisted cursor after at least one successful permitted retrieval.
                    updates = {
                        "attempts": (query.get("attempts") or 0) + 1,
                        "yield_count": (query.get("yield_count") or 0) + new,
                        "last_run_at": now(),
                    }
                    if successes:
                        updates.update(
                            cursor=json.dumps(cursors),
                            cache_until=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                        )
                    store.update("queries", query["id"], updates)
                    store.update(
                        "research_runs",
                        execution["id"],
                        {
                            "checkpoint": {"last_query_id": query["id"]},
                            "requests": t.requests,
                            "observations": len(collected),
                        },
                    )
                if task:
                    store.update(
                        "research_queue",
                        task["id"],
                        {
                            "status": "completed" if collected else "pending",
                            "last_error": None if collected else "No new observations; see source health",
                            "due_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                        },
                    )
                if not collected:
                    store.alert(
                        "no_live_discoveries",
                        "No new observations were collected. Check source/API health; no synthetic results substituted.",
                        run_id=execution["id"],
                    )
            if command in {"discover", "analyze", "deep-dive"}:
                changed = rules_analysis(store, collected if command == "discover" else None, execution["id"])
                if live and changed:
                    router = ModelRouter(t)
                    changed = [i for i in changed if i["id"] not in attempted_ai]
                    observations = collected or store.list("raw_observations", limit=12)
                    role = "deep" if command == "deep-dive" else "fast"
                    batch, identity = router.analyze(changed[:1], observations, role=role)
                    if batch:
                        router.apply(batch, identity)
                        enqueue_ai(store, changed[1:], role=role, run_id=execution["id"])
                    else:
                        enqueue_ai(store, changed, role=role, run_id=execution["id"])
                        diagnostics.append(
                            {"analysis": "rules-only; no authorized configured model succeeded"}
                        )
            if command in {"enrich", "deep-dive"}:
                enrich(store)
            if command == "challenge":
                challenge(store)
                if live:
                    candidates = [
                        i for i in store.all("opportunities") if i.get("favorite") or i.get("pinned")
                    ][:1]
                    original = {i.get("model_version") for i in candidates if i.get("model_version")}
                    router = ModelRouter(t)
                    result, identity = router.analyze(
                        candidates,
                        store.list("raw_observations", limit=12),
                        "critic",
                        independent_from=next(iter(original)) if len(original) == 1 else None,
                    )
                    if result and identity not in original:
                        router.apply(result, identity, critique=True)
                    elif candidates:
                        enqueue_ai(store, candidates, role="critic", run_id=execution["id"])
            retain(store)
            store.update(
                "research_runs",
                execution["id"],
                {
                    "status": "completed",
                    "finished_at": now(),
                    "requests": t.requests,
                    "observations": len(collected),
                    "diagnostics": diagnostics,
                },
            )
            return {
                "run_id": execution["id"],
                "status": "completed",
                "new_observations": len(collected),
                "requests": t.requests,
                "mode": "synthetic-demo" if store.settings.demo else "live",
                "diagnostics": diagnostics,
            }
        except Exception:
            store.update(
                "research_runs",
                execution["id"],
                {
                    "status": "failed",
                    "finished_at": now(),
                    "requests": t.requests,
                    "diagnostics": [{"error": "worker failed; no secrets or source documents logged"}],
                },
            )
            raise
        finally:
            t.close()
