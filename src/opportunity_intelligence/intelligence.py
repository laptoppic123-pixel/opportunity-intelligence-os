from difflib import SequenceMatcher
import re
from .safety import clean, digest, normalize_url
from .schema import now
from .scoring import save_score


def ingest(store, source, observation, *, query=None, run_id=None, synthetic=False):
    url = normalize_url(observation.url)
    excerpt = clean(observation.excerpt)
    title = clean(observation.title, 240)
    if (
        query
        and query.get("approach") == "physical"
        and re.search(
            r"\b(firearms|ammunition|illegal drugs|explosives|tobacco|vapes|pornography)\b",
            title + " " + excerpt,
            re.I,
        )
    ):
        raise ValueError("Excluded physical-product sector")
    content_hash = digest((title + " " + excerpt).casefold())
    for field, value in [
        ("source_item_id", observation.item_id),
        ("normalized_url", url),
        ("content_hash", content_hash),
    ]:
        filters = {field: value}
        if field == "source_item_id":
            filters["source_id"] = source["id"]
        if store.list("raw_observations", limit=1, **filters):
            return None
    # Similar reposts must not become independent customers.
    for old in store.list("raw_observations", limit=500):
        if (
            excerpt
            and old.get("excerpt")
            and SequenceMatcher(None, excerpt.casefold(), old["excerpt"].casefold()).ratio() > 0.94
        ):
            return None
    row = store.add(
        "raw_observations",
        {
            "source_id": source["id"],
            "source_item_id": str(observation.item_id),
            "url": observation.url,
            "normalized_url": url,
            "published_at": observation.published_at,
            "observed_at": now(),
            "title": title,
            "excerpt": excerpt,
            "content_hash": content_hash,
            "author_hash": observation.author_hash,
            "access_status": "synthetic" if synthetic else "public_api_excerpt",
            "license": observation.license,
            "provenance": {
                "source_item_id": str(observation.item_id),
                "query_id": query["id"] if query else None,
                "dimensions": query.get("dimensions", {}) if query else {},
                "approach": query.get("approach") if query else None,
                "metadata": observation.metadata,
            },
            "run_id": run_id,
            "synthetic": synthetic,
            "archived": False,
        },
    )
    return row


def rules_analysis(store, observations=None, run_id=None):
    observations = observations if observations is not None else store.all("raw_observations")
    changed = []
    for obs in observations:
        if obs.get("archived"):
            continue
        provenance = obs.get("provenance") or {}
        dims = provenance.get("dimensions") or {}
        symptom = obs.get("title") or "Unclassified reported problem"
        tokens = re.findall(r"[a-z]{3,}", (symptom + " " + (obs.get("excerpt") or "")).lower())
        stop = {"the", "and", "with", "this", "that", "have", "from", "would", "could", "please", "their"}
        key = " ".join(sorted(set(tokens) - stop)[:6]) or obs["content_hash"]
        # A shared workflow/industry is only a candidate cluster, not proof of a shared root cause.
        fingerprint = digest([dims.get("industry"), dims.get("workflow"), key])
        for candidate in store.list("problem_clusters", limit=500):
            if (
                candidate.get("job") == dims.get("workflow")
                and candidate.get("buyer") == dims.get("buyer")
                and SequenceMatcher(None, (candidate.get("name") or "").lower(), symptom.lower()).ratio()
                > 0.65
            ):
                fingerprint = candidate["fingerprint"]
                break
        cluster_id = store.stable_id("cluster", fingerprint)
        excerpt = obs.get("excerpt") or ""
        cause = re.search(r"(?:because|caused by)\s+([^.!?]{8,180})", excerpt, re.I)
        workaround = re.search(
            r"(?:workaround is|currently use|currently using)\s+([^.!?]{4,120})", excerpt, re.I
        )
        timecost = re.search(r"\b(\d+)\s+(minutes?|hours?)\b", excerpt, re.I)
        cluster = store.upsert(
            "problem_clusters",
            {
                "id": cluster_id,
                "fingerprint": fingerprint,
                "name": symptom,
                "job": dims.get("workflow"),
                "symptom": obs.get("excerpt"),
                "root_cause": cause[1] if cause else None,
                "buyer": dims.get("buyer"),
                "workaround": workaround[1] if workaround else None,
                "time_cost_minutes": float(timecost[1])
                * (60 if timecost[2].lower().startswith("hour") else 1)
                if timecost
                else None,
                "unknowns": [
                    "Root cause and buyer identity need verification",
                    "Frequency and time cost are not established",
                ],
            },
            unique=("fingerprint",),
        )
        store.upsert(
            "cluster_observations",
            {"cluster_id": cluster_id, "observation_id": obs["id"]},
            unique=("cluster_id", "observation_id"),
        )
        linked = store.list("cluster_observations", cluster_id=cluster_id)
        linked_obs = [store.get("raw_observations", link["observation_id"]) for link in linked]
        authors = {o["author_hash"] for o in linked_obs if o and o.get("author_hash")}
        store.update("problem_clusters", cluster_id, {"independent_customers": len(authors)})
        replay = digest([cluster_id, "digital-v2"])
        prior = store.list("opportunities", replay_hash=replay, limit=1)
        if prior:
            opportunity = prior[0]
        else:
            opportunity = store.add(
                "opportunities",
                {
                    "cluster_id": cluster_id,
                    "title": "Investigate: " + symptom[:140],
                    "problem": obs.get("excerpt"),
                    "solution": "Hypothesis: a focused tool or service addressing the reported workflow; validate with the buyer.",
                    "buyer": dims.get("buyer"),
                    "industry": dims.get("industry"),
                    "category": provenance.get("approach") or "pain",
                    "geography": dims.get("geography"),
                    "language": dims.get("language"),
                    "track": "physical" if provenance.get("approach") == "physical" else "digital",
                    "status": "speculative",
                    "labels": [],
                    "favorite": False,
                    "pinned": False,
                    "mvp": "Interview the affected buyer, reproduce the problem, and test one narrow workflow.",
                    "distribution": [
                        "Identify 5–10 relevant interview candidates in the cited source community; do not send automatically."
                    ],
                    "unknowns": [
                        "Willingness to pay",
                        "Existing solutions",
                        "Buyer access",
                        "Implementation effort",
                    ],
                    "weaknesses": ["Public discussions are not direct buyer validation."],
                    "analysis_method": "rules-only",
                    "model_version": None,
                    "prompt_version": "rules-v2",
                    "synthetic": bool(obs["synthetic"]),
                    "novelty": None,
                    "upside": None,
                    "confidence": None,
                    "effort": None,
                    "customer_validated": False,
                    "run_id": run_id,
                    "replay_hash": replay,
                },
            )
        claim_type = "hypothesis" if obs["synthetic"] else "source_fact"
        claim = (
            "Synthetic demonstration statement"
            if obs["synthetic"]
            else "This source publicly reports the excerpted issue; demand and root cause are unverified."
        )
        store.upsert(
            "opportunity_evidence",
            {
                "opportunity_id": opportunity["id"],
                "observation_id": obs["id"],
                "claim": claim,
                "claim_type": claim_type,
                "quote": obs.get("excerpt"),
                "stance": "counterevidence" if provenance.get("approach") == "counterevidence" else "support",
                "assessment": "synthetic" if obs["synthetic"] else "public discussion, not interview",
            },
            unique=("opportunity_id", "observation_id", "claim_type", "claim"),
        )
        if len(authors) >= 2 and opportunity.get("status") == "speculative" and not obs["synthetic"]:
            store.update("opportunities", opportunity["id"], {"status": "evidence-backed"})
        if opportunity.get("track") == "physical":
            store.update(
                "opportunities",
                opportunity["id"],
                {
                    "unknowns": list(
                        dict.fromkeys(
                            (opportunity.get("unknowns") or [])
                            + [
                                "Supplier availability and product safety",
                                "Fulfillment and shipping costs",
                                "Returns and compatibility economics",
                            ]
                        )
                    )
                },
            )
        dimensions = {"recurrence": min(5, len(authors)) if len(authors) > 1 else None}
        save_score(store, opportunity, dimensions, [o["id"] for o in linked_obs if o])
        changed.append(opportunity)
    return changed


def enrich(store, opportunities=None):
    count = 0
    for idea in opportunities or store.all("opportunities"):
        # Deep enrichment is targeted; preserve low-evidence ideas instead of deleting them.
        for evidence in store.list("opportunity_evidence", opportunity_id=idea["id"]):
            obs = (
                store.get("raw_observations", evidence.get("observation_id"))
                if evidence.get("observation_id")
                else None
            )
            if not obs or obs.get("synthetic"):
                continue
            text = obs.get("excerpt") or ""
            match = re.search(
                r"\b(?:paid|spent|budget|contract)\b.{0,45}?([$€£])\s*([\d,]+(?:\.\d{1,2})?)", text, re.I
            )
            if match:
                existing = store.list("spending_signals", opportunity_id=idea["id"], observation_id=obs["id"])
                if not existing:
                    store.add(
                        "spending_signals",
                        {
                            "opportunity_id": idea["id"],
                            "observation_id": obs["id"],
                            "kind": "public_budget_or_spend_reference",
                            "amount": float(match[2].replace(",", "")),
                            "currency": {"$": "$ (currency unspecified)", "€": "EUR", "£": "GBP"}[match[1]],
                            "claim_type": "source_fact",
                            "excerpt": match[0],
                        },
                    )
                    count += 1
            if (obs.get("provenance") or {}).get("approach") == "reverse_competitor":
                from urllib.parse import urlsplit

                candidate = ((obs.get("provenance") or {}).get("metadata") or {}).get("original_link") or obs[
                    "url"
                ]
                host = urlsplit(candidate).hostname or ""
                if host and host not in {"github.com", "news.ycombinator.com", "stackoverflow.com"}:
                    competitors = store.list(
                        "competitors", opportunity_id=idea["id"], observation_id=obs["id"]
                    )
                    competitor = (
                        competitors[0]
                        if competitors
                        else store.add(
                            "competitors",
                            {
                                "opportunity_id": idea["id"],
                                "observation_id": obs["id"],
                                "name": "Candidate substitute: " + host,
                                "url": candidate,
                                "features": text,
                                "limitations": "Relevance and feature gap require verification; this is a candidate, not a confirmed competitor.",
                            },
                        )
                    )
                    price = re.search(
                        r"([$€£])\s*([\d,]+(?:\.\d{1,2})?)\s*(?:/|per\s+)(month|year|user|seat)", text, re.I
                    )
                    if price and not store.list(
                        "pricing_snapshots", competitor_id=competitor["id"], observation_id=obs["id"]
                    ):
                        store.add(
                            "pricing_snapshots",
                            {
                                "competitor_id": competitor["id"],
                                "observation_id": obs["id"],
                                "amount": float(price[2].replace(",", "")),
                                "currency": {"$": None, "€": "EUR", "£": "GBP"}[price[1]],
                                "billing_period": price[3].lower(),
                                "observed_at": now(),
                            },
                        )
    return count


def challenge(store, opportunities=None):
    count = 0
    for idea in opportunities or store.all("opportunities"):
        if not (idea.get("favorite") or idea.get("pinned")):
            continue
        query = f"{idea['title']} existing solution alternative counterevidence"
        if not store.list("research_queue", query=query, status="pending"):
            store.add(
                "research_queue",
                {
                    "opportunity_id": idea["id"],
                    "kind": "challenge",
                    "query": query,
                    "priority": 90,
                    "status": "pending",
                    "due_at": now(),
                    "attempts": 0,
                },
            )
            count += 1
        weak = list(
            dict.fromkeys(
                (idea.get("weaknesses") or [])
                + ["Independent counter-evidence research is queued; criticism is not a rejection."]
            )
        )
        store.update("opportunities", idea["id"], {"weaknesses": weak})
    return count
