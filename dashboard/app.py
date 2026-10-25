"""Local owner dashboard. Run with Streamlit; never publish this process publicly."""

from datetime import date, datetime
import csv
from dataclasses import replace
from io import StringIO
import json
import streamlit as st
from opportunity_intelligence.config import Settings, ROOT
from opportunity_intelligence.store import Store
from opportunity_intelligence.demo import seed_demo
from opportunity_intelligence.services import (
    ideas_view,
    edit_idea,
    add_note,
    queue_research,
    manual_idea,
    import_ideas,
)
from opportunity_intelligence.providers import ProviderRegistry
from opportunity_intelligence.exports import project, xlsx_bytes, csv_bytes, markdown
from opportunity_intelligence.safety import public_url
from opportunity_intelligence.schema import now

st.set_page_config(page_title="Opportunity Intelligence OS", page_icon="◈", layout="wide")
st.markdown(
    """<style>.block-container{padding-top:2rem;max-width:1500px}h1{letter-spacing:-.045em}
[data-testid="stMetric"]{background:white;border:1px solid #e1e8f0;border-radius:12px;padding:18px}
[data-testid="stSidebar"]{border-right:1px solid #dbe4ee}.stCaption{color:#56677a}</style>""",
    unsafe_allow_html=True,
)

settings = Settings.load()
st.sidebar.markdown("## ◈ Opportunity OS")
st.sidebar.caption("INTELLIGENCE WORKSPACE · V2.0")
demo = st.sidebar.toggle(
    "Use synthetic demo",
    value=settings.demo,
    help="Explicitly opens a separate local SQLite fixture database. No network calls.",
)


@st.cache_resource
def connect(demo_mode, data_dir):
    cfg = replace(Settings.load(), demo=demo_mode, data_dir=__import__("pathlib").Path(data_dir))
    store = Store(cfg)
    if demo_mode:
        seed_demo(store)
    return store


if not demo and (
    not settings.secret_key
    or not settings.supabase_url
    or not settings.owner
    or not settings.activated
    or not settings.live
):
    st.title("Your research workspace is ready")
    st.info("READY_FOR_CREDENTIALS · Live research, paid APIs and schedules are disabled.")
    st.write(
        "Choose **Use synthetic demo** to explore the application offline, or follow CONNECTION_CHECKLIST.md before activation."
    )
    st.caption(
        "The dashboard is a local server bound to 127.0.0.1. Secret values are never shown in this interface."
    )
    st.stop()

try:
    store = connect(demo, str(settings.data_dir))
except (ValueError, RuntimeError, PermissionError):
    st.error(
        "Database unavailable. Run oi doctor and review the connection checklist. No demo data was substituted."
    )
    st.stop()

if demo:
    st.warning(
        "DEMO / SYNTHETIC DATA — all examples, source links and customer scenarios are fictional. No live discoveries or buyer validation."
    )
else:
    st.caption("CANONICAL SUPABASE DATA · public source discussions are not customer interviews")
st.sidebar.caption("Rules-only works without AI keys. Unknown values remain unknown.")
pages = [
    "Overview",
    "Explore / Search",
    "Opportunity Detail",
    "Speculative Gems",
    "Idea Comparison",
    "Research Queue",
    "Source / API Health",
    "Usage & Budget",
    "Favorites / Owner Notes",
    "Export Center",
]
page = st.sidebar.radio("Workspace", pages, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("Manual and bounded cloud jobs · no background server")
ideas = ideas_view(store)
by_id = {i["id"]: i for i in ideas}


def table(rows, columns=None):
    if not rows:
        st.info("No matching records yet.")
        return
    st.dataframe(
        [{k: r.get(k) for k in columns} for r in rows] if columns else rows,
        use_container_width=True,
        hide_index=True,
    )


def label(idea):
    return idea["title"] + (" ★" if idea.get("favorite") else "")


def select_idea(key="idea"):
    if not ideas:
        st.info("No ideas yet. Add a manual hypothesis or queue research.")
        return None
    identifier = st.selectbox("Opportunity", list(by_id), format_func=lambda x: label(by_id[x]), key=key)
    return by_id[identifier]


def detail(idea):
    st.subheader(idea["title"])
    a, b, c, d = st.columns(4)
    a.metric(
        "Assessed score", "Unknown" if idea["weighted_score"] is None else f"{idea['weighted_score']:.1f}/100"
    )
    b.metric("Scoring coverage", f"{idea['coverage']}%")
    c.metric("Evidence confidence", "Unknown" if idea.get("confidence") is None else str(idea["confidence"]))
    d.metric("Direct buyer validation", "Recorded" if idea.get("customer_validated") else "Not recorded")
    st.caption(
        f"Track: {idea.get('track')} · Status: {idea.get('status')} · Method: {idea.get('analysis_method')} · Model: {idea.get('model_version') or 'none'}"
    )
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Problem")
        st.write(idea.get("problem") or "Unknown")
        st.markdown("#### Product hypothesis")
        st.write(idea.get("solution") or "Unknown")
        st.markdown("#### Narrow MVP")
        st.write(idea.get("mvp") or "Needs research")
        st.markdown("#### First buyer channels")
        st.write(idea.get("distribution") or ["Unknown"])
        st.markdown("#### Evidence and original sources")
        evidence = store.list("opportunity_evidence", opportunity_id=idea["id"])
        for item in evidence:
            obs = (
                store.get("raw_observations", item["observation_id"]) if item.get("observation_id") else None
            )
            with st.expander(item["claim_type"] + " · " + item.get("stance", "support"), expanded=True):
                st.write(item["claim"])
                if item.get("quote"):
                    st.text(item["quote"])
                if obs:
                    st.caption(
                        f"{obs.get('published_at') or 'Publication date unknown'} · {obs.get('license')}"
                    )
                    try:
                        public_url(obs["url"])
                        st.link_button(
                            "Original source" if not obs.get("synthetic") else "Fictional demonstration link",
                            obs["url"],
                        )
                    except ValueError:
                        st.caption("Source URL unavailable")
        if not evidence:
            st.info("Owner hypothesis: no independent source evidence recorded.")
    with right:
        st.markdown("#### Unknowns / weaknesses")
        st.write(idea.get("unknowns") or ["Unknown"])
        st.write(idea.get("weaknesses") or [])
        st.markdown("#### Separate assessments")
        table([{k: idea.get(k) for k in ["novelty", "upside", "effort"]}])
        with st.form("edit-" + idea["id"]):
            favorite = st.checkbox("Favorite", value=bool(idea.get("favorite")))
            pinned = st.checkbox("Pin for deeper research", value=bool(idea.get("pinned")))
            labels = st.text_input("Labels", value=", ".join(idea.get("labels") or []))
            statuses = ["speculative", "evidence-backed", "watchlist", "emerging", "revived", "archived"]
            status = st.selectbox(
                "Status",
                statuses,
                index=statuses.index(idea["status"]) if idea.get("status") in statuses else 0,
            )
            if st.form_submit_button("Save idea changes"):
                edit_idea(
                    store,
                    idea["id"],
                    favorite=favorite,
                    pinned=pinned,
                    labels=[x.strip() for x in labels.split(",") if x.strip()],
                    status=status,
                )
                st.success("Saved")
                st.rerun()
        if st.button("Research this idea next", key="research-" + idea["id"]):
            queue_research(store, idea["title"], opportunity_id=idea["id"], priority=90)
            st.success("Queued for the next authorized worker run.")
    tabs = st.tabs(["Competitors & prices", "Spending evidence", "Notes & validation", "Score history"])
    with tabs[0]:
        competitors = store.list("competitors", opportunity_id=idea["id"])
        table(competitors, ["name", "url", "features", "limitations"])
        table([p for c in competitors for p in store.list("pricing_snapshots", competitor_id=c["id"])])
    with tabs[1]:
        table(
            store.list("spending_signals", opportunity_id=idea["id"]),
            ["kind", "amount", "currency", "claim_type", "excerpt", "observation_id"],
        )
    with tabs[2]:
        table(
            store.list("owner_feedback", opportunity_id=idea["id"]),
            ["kind", "note", "genuine_buyer_feedback", "created_at"],
        )
        with st.form("note-" + idea["id"]):
            note = st.text_area("Owner note / actual buyer feedback")
            kind = st.selectbox("Feedback type", ["note", "interview", "pilot", "commitment"])
            genuine = st.checkbox(
                "This records genuine direct buyer feedback, not a public discussion or synthetic example"
            )
            url = st.text_input("Optional feedback evidence URL")
            if st.form_submit_button("Save note"):
                try:
                    add_note(store, idea["id"], note, kind, genuine, url or None)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with st.form("experiment-" + idea["id"]):
            hypothesis = st.text_input("Validation experiment hypothesis")
            criteria = st.text_input("Measurable success criteria")
            if st.form_submit_button("Record experiment") and hypothesis and criteria:
                store.add(
                    "validation_experiments",
                    {
                        "opportunity_id": idea["id"],
                        "kind": "owner-designed",
                        "hypothesis": hypothesis[:500],
                        "success_criteria": criteria[:500],
                        "status": "proposed",
                    },
                )
                st.rerun()
        table(
            store.list("validation_experiments", opportunity_id=idea["id"]),
            ["hypothesis", "success_criteria", "status", "result"],
        )
    with tabs[3]:
        table(store.list("score_history", opportunity_id=idea["id"]), ["created_at", "event", "snapshot"])


st.title(page)
if page == "Overview":
    st.caption("Evidence first. Keep promising hypotheses; make uncertainty visible.")
    a, b, c, d = st.columns(4)
    a.metric("Opportunities", len(ideas))
    b.metric("Speculative gems", sum(i["status"] == "speculative" for i in ideas))
    c.metric("Favorites", sum(bool(i.get("favorite")) for i in ideas))
    d.metric("Pending research", len(store.list("research_queue", status="pending")))
    runs = store.all("research_runs")
    observations = store.all("raw_observations")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Research activity")
        daily = {}
        for row in observations:
            daily[row["observed_at"][:10]] = daily.get(row["observed_at"][:10], 0) + 1
        if daily:
            st.bar_chart(
                [{"date": k, "observations": v} for k, v in sorted(daily.items())], x="date", y="observations"
            )
        else:
            st.info("No observed-source activity. Live results are never simulated.")
    with right:
        st.subheader("Track mix")
        st.bar_chart(
            [
                {"track": track, "ideas": sum(i["track"] == track for i in ideas)}
                for track in ["digital", "physical"]
            ],
            x="track",
            y="ideas",
        )
    st.subheader("Recent research runs")
    table(runs[-10:], ["command", "status", "started_at", "requests", "observations", "diagnostics"])
    st.subheader("System notices")
    table(store.list("system_alerts", resolved=False), ["severity", "code", "message", "created_at"])
elif page in {"Explore / Search", "Speculative Gems", "Favorites / Owner Notes"}:
    rows = ideas
    if page == "Explore / Search":
        view = st.selectbox(
            "Research view",
            [
                "All opportunities",
                "Promising / Evidence-backed",
                "Speculative Gems",
                "Spending-first",
                "Emerging",
                "Affordable MVPs",
                "Watchlist",
                "Owner Favorites",
            ],
        )
        if view == "Promising / Evidence-backed":
            rows = [
                i
                for i in rows
                if i.get("status") == "evidence-backed"
                or (i.get("coverage", 0) >= 50 and (i.get("weighted_score") or 0) >= 60)
            ]
        if view == "Speculative Gems":
            rows = [i for i in rows if i.get("status") == "speculative"]
        if view == "Spending-first":
            backed = {s["opportunity_id"] for s in store.all("spending_signals")}
            rows = [i for i in rows if i["id"] in backed]
        if view == "Emerging":
            rows = [i for i in rows if i.get("status") == "emerging" or i.get("category") == "emerging"]
        if view == "Affordable MVPs":
            rows = [i for i in rows if i.get("effort") is not None and i["effort"] <= 2]
        if view == "Watchlist":
            rows = [i for i in rows if i.get("status") == "watchlist"]
        if view == "Owner Favorites":
            rows = [i for i in rows if i.get("favorite")]
    if page == "Speculative Gems":
        rows = [i for i in rows if i["status"] == "speculative"]
    if page == "Favorites / Owner Notes":
        rows = [i for i in rows if i.get("favorite")]
    top = st.columns(3)
    query = top[0].text_input("Search problem, product or labels")
    track = top[1].selectbox("Evaluation track", ["digital", "physical"])
    sort = top[2].selectbox("Sort", ["Newest", "Assessed score", "Coverage"])
    with st.expander("Buyer, industry, geography, evidence and date filters"):
        filters = {}
        for field in ["buyer", "industry", "category", "geography"]:
            filters[field] = st.multiselect(
                field.replace("_", " ").title(), sorted({i[field] for i in ideas if i.get(field)})
            )
        low = st.slider("Minimum assessed score", 0, 100, 0)
        conf = st.slider("Minimum evidence confidence (0–5)", 0, 5, 0)
        include_unknown = st.checkbox("Include unknown scores/confidence", True)
        start = st.date_input("Created on or after", value=date(2020, 1, 1))
        end = st.date_input("Created on or before", value=date.today())
    rows = [
        i
        for i in rows
        if i["track"] == track
        and (not query or query.casefold() in json.dumps(i).casefold())
        and all(not values or i.get(field) in values for field, values in filters.items())
        and start.isoformat() <= i["created_at"][:10] <= end.isoformat()
        and (
            (include_unknown and i["weighted_score"] is None)
            or (i["weighted_score"] is not None and i["weighted_score"] >= low)
        )
        and (
            (include_unknown and i.get("confidence") is None)
            or (i.get("confidence") is not None and i["confidence"] >= conf)
        )
    ]
    rows = sorted(
        rows,
        key=lambda i: i["created_at"]
        if sort == "Newest"
        else i.get("weighted_score" if sort == "Assessed score" else "coverage") or -1,
        reverse=True,
    )
    table(
        rows,
        [
            "id",
            "title",
            "buyer",
            "industry",
            "category",
            "status",
            "weighted_score",
            "coverage",
            "confidence",
            "favorite",
            "analysis_method",
        ],
    )
    st.caption(
        "Digital and physical tracks are shown separately. Scores with partial coverage are not evidence of success."
    )
    if page == "Explore / Search":
        with st.expander("Add or import an owner hypothesis"):
            with st.form("manual-idea"):
                title = st.text_input("Title")
                problem = st.text_area("Problem statement")
                buyer = st.text_input("Buyer", value="unknown")
                industry = st.text_input("Industry", value="unknown")
                manual_track = st.selectbox("New idea track", ["digital", "physical"])
                if st.form_submit_button("Add hypothesis"):
                    try:
                        manual_idea(store, title, problem, buyer=buyer, industry=industry, track=manual_track)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            upload = st.file_uploader(
                "Import JSON list or CSV (title, problem, buyer, industry, track)", type=["json", "csv"]
            )
            if upload and st.button("Import owner hypotheses"):
                try:
                    text = upload.getvalue().decode("utf-8-sig")
                    records = (
                        json.loads(text)
                        if upload.name.endswith(".json")
                        else list(csv.DictReader(StringIO(text)))
                    )
                    import_ideas(store, records)
                    st.rerun()
                except (ValueError, UnicodeError):
                    st.error("Invalid import. Supply at most 100 objects with title and problem.")
elif page == "Opportunity Detail":
    idea = select_idea()
    if idea:
        detail(idea)
elif page == "Idea Comparison":
    selected = st.multiselect(
        "Select 2–5 ideas from the same evaluation track",
        list(by_id),
        format_func=lambda x: label(by_id[x]),
        max_selections=5,
    )
    if len(selected) < 2:
        st.info("Select at least two ideas to compare.")
    elif len({by_id[x]["track"] for x in selected}) > 1:
        st.warning("Compare physical candidates separately from digital opportunities.")
    else:
        for column, identifier in zip(st.columns(len(selected)), selected):
            with column:
                idea = by_id[identifier]
                st.subheader(idea["title"])
                for field in [
                    "buyer",
                    "problem",
                    "solution",
                    "mvp",
                    "weighted_score",
                    "coverage",
                    "novelty",
                    "upside",
                    "confidence",
                    "effort",
                    "unknowns",
                    "weaknesses",
                ]:
                    st.markdown("**" + field.replace("_", " ").title() + "**")
                    st.write(idea.get(field) if idea.get(field) is not None else "Unknown")
elif page == "Research Queue":
    st.info(
        "Tasks are saved to the database for the next authorized cloud job. This does not start a background server."
    )
    with st.form("queue"):
        query = st.text_area("Target niche, competitor, topic or skeptical research question")
        kind = st.selectbox("Task type", ["topic", "niche", "competitor", "challenge"])
        priority = st.slider("Priority", 1, 100, 50)
        if st.form_submit_button("Queue research"):
            try:
                queue_research(store, query, kind, priority=priority)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    tasks = store.all("research_queue")
    table(tasks, ["id", "query", "kind", "priority", "status", "due_at", "attempts", "last_error"])
    if tasks:
        selected = st.selectbox(
            "Task to manage",
            [q["id"] for q in tasks],
            format_func=lambda x: next(q["query"] for q in tasks if q["id"] == x),
        )
        a, b = st.columns(2)
        if a.button("Return task to pending"):
            store.update("research_queue", selected, {"status": "pending", "due_at": now()})
            st.rerun()
        if b.button("Cancel queued task"):
            store.update("research_queue", selected, {"status": "cancelled"})
            st.rerun()
elif page == "Source / API Health":
    st.caption(
        "Capability is configured before keys. Enabled does not override the global live/activation flags."
    )
    table(ProviderRegistry(store).status())
    rows = store.all("source_registry")
    if rows:
        selected = st.selectbox(
            "Provider to review",
            [r["id"] for r in rows],
            format_func=lambda x: next(r["name"] for r in rows if r["id"] == x),
        )
        st.write(next(r["legal_access_notes"] for r in rows if r["id"] == selected))
        if st.button("Reset reviewed provider circuit breaker"):
            store.update("source_registry", selected, {"failure_count": 0, "last_error": None})
            st.success("Reset. This does not enable the provider or grant access.")
elif page == "Usage & Budget":
    a, b, c = st.columns(3)
    usage = store.all("provider_usage")
    a.metric("Actual recorded external cost", f"${sum(u.get('actual_cost') or 0 for u in usage):.4f}")
    b.metric("Monthly ceiling", f"${store.settings.monthly_limit}")
    c.metric("Internal paid stop", f"${store.settings.paid_stop}")
    st.warning(
        "Paid mode is "
        + ("ON" if store.settings.paid else "OFF")
        + ". Internal estimates do not guarantee vendor charges. Configure vendor-side limits; no auto top-ups."
    )
    table(store.all("budget_months"))
    table(store.all("source_quotas"))
    table(usage, ["source_id", "status", "estimated_cost", "actual_cost", "credit_type", "created_at"])
elif page == "Export Center":
    st.caption(
        "All formats below derive from one snapshot of the same database records shown in this dashboard."
    )
    if st.button("Prepare current database exports"):
        sheets = project(store)
        st.session_state["exports"] = {
            "xlsx": xlsx_bytes(sheets, demo=demo),
            "md": markdown(sheets),
            "csv": csv_bytes(sheets["Ideas"]),
            "count": len(sheets["Ideas"]),
        }
    if "exports" in st.session_state:
        exports = st.session_state["exports"]
        st.success(f"Prepared snapshot with {exports['count']} ideas. Refresh after editing records.")
        st.download_button(
            "Download Excel workbook",
            exports["xlsx"],
            "opportunities.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button("Download ideas CSV", exports["csv"], "ideas.csv", "text/csv")
        st.download_button("Download research summary", exports["md"], "research-summary.md", "text/markdown")
