"""UI, CLI and exports use the same owner-scoped records and projections."""

import json
from uuid import uuid4
from .safety import clean, normalize_url
from .schema import now


def ideas_view(store):
    scores = {s["opportunity_id"]: s for s in store.all("scores")}
    return [
        {
            **idea,
            "weighted_score": scores.get(idea["id"], {}).get("weighted_score"),
            "coverage": scores.get(idea["id"], {}).get("coverage", 0),
        }
        for idea in store.all("opportunities")
    ]


def queue_research(store, query, kind="topic", opportunity_id=None, priority=50):
    query = clean(query, 400)
    if not query:
        raise ValueError("A research question is required")
    if kind not in {"topic", "niche", "competitor", "challenge"}:
        raise ValueError("Unsupported task type")
    if opportunity_id and not store.get("opportunities", opportunity_id):
        raise ValueError("Unknown idea")
    return store.add(
        "research_queue",
        {
            "query": query,
            "kind": kind,
            "opportunity_id": opportunity_id,
            "priority": max(1, min(100, int(priority))),
            "status": "pending",
            "due_at": now(),
            "attempts": 0,
        },
    )


def edit_idea(store, identifier, *, favorite=None, labels=None, status=None, pinned=None):
    if not store.get("opportunities", identifier):
        raise ValueError("Unknown idea")
    changes = {}
    if favorite is not None:
        changes["favorite"] = bool(favorite)
    if pinned is not None:
        changes["pinned"] = bool(pinned)
    if labels is not None:
        changes["labels"] = [clean(s, 50) for s in labels][:20]
    if status is not None:
        if status not in {"speculative", "evidence-backed", "watchlist", "emerging", "revived", "archived"}:
            raise ValueError("Unsupported status")
        changes["status"] = status
    store.update("opportunities", identifier, changes)


def add_note(store, identifier, note, kind="note", genuine=False, evidence_url=None):
    idea = store.get("opportunities", identifier)
    if not idea or not clean(note):
        raise ValueError("Idea and note are required")
    if kind not in {"note", "interview", "pilot", "commitment"}:
        raise ValueError("Unknown feedback kind")
    if evidence_url:
        normalize_url(evidence_url)
    row = store.add(
        "owner_feedback",
        {
            "opportunity_id": identifier,
            "note": clean(note, 1600),
            "kind": kind,
            "genuine_buyer_feedback": bool(genuine and kind != "note" and not idea.get("synthetic")),
            "evidence_url": evidence_url,
        },
    )
    if row["genuine_buyer_feedback"]:
        store.update("opportunities", identifier, {"customer_validated": True})
    return row


def manual_idea(store, title, problem, *, buyer="unknown", industry="unknown", track="digital"):
    if not clean(title) or not clean(problem):
        raise ValueError("Title and problem required")
    if track not in {"digital", "physical"}:
        raise ValueError("Invalid track")
    return store.add(
        "opportunities",
        {
            "title": clean(title, 180),
            "problem": clean(problem),
            "buyer": clean(buyer),
            "industry": clean(industry),
            "track": track,
            "category": "owner hypothesis",
            "status": "speculative",
            "labels": [],
            "favorite": False,
            "pinned": False,
            "synthetic": store.settings.demo,
            "customer_validated": False,
            "analysis_method": "owner hypothesis",
            "unknowns": ["Requires independent evidence"],
            "weaknesses": [],
            "distribution": [],
            "replay_hash": str(uuid4()),
        },
    )


def import_ideas(store, records):
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("Import must contain at most 100 idea objects")
    for record in records:
        if not isinstance(record, dict) or not record.get("title") or not record.get("problem"):
            raise ValueError("Each idea needs title and problem")
    return [
        manual_idea(
            store,
            r["title"],
            r["problem"],
            buyer=r.get("buyer", "unknown"),
            industry=r.get("industry", "unknown"),
            track=r.get("track", "digital"),
        )
        for r in records
    ]
