"""One relational schema shared by offline SQLite and checked-in PostgreSQL DDL."""

from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Text,
    JSON,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Index,
)

metadata = MetaData()


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid4())


def table(name, *columns, **kwargs):
    return Table(
        name,
        metadata,
        Column("id", String(100), primary_key=True),
        Column("owner_id", String(36), nullable=False),
        Column("created_at", String(40), nullable=False),
        Column("updated_at", String(40), nullable=False),
        *columns,
        **kwargs,
    )


def text(name, nullable=True):
    return Column(name, Text, nullable=nullable)


def ref(name, target, nullable=True):
    return Column(name, String(100), ForeignKey(target + ".id"), nullable=nullable)


def jsoncol(name):
    return Column(name, JSON)


source_registry = table(
    "source_registry",
    text("name", False),
    Column("enabled", Boolean),
    Column("credentials_present", Boolean),
    Column("current_terms_checked", Boolean),
    jsoncol("capabilities"),
    Column("estimated_cost", Float),
    Column("daily_quota", Integer),
    Column("monthly_quota", Integer),
    text("reset_date"),
    Column("failure_count", Integer),
    text("last_success"),
    text("last_error"),
    Column("added_information_value", Float),
    Column("priority", Integer),
    text("legal_access_notes"),
    jsoncol("config"),
    UniqueConstraint("owner_id", "name"),
)
source_quotas = table(
    "source_quotas",
    ref("source_id", "source_registry", False),
    text("period", False),
    Column("used", Integer),
    Column("limit_value", Integer),
    text("reset_at"),
    UniqueConstraint("owner_id", "source_id", "period"),
)
queries = table(
    "queries",
    text("query_hash", False),
    text("text", False),
    jsoncol("dimensions"),
    text("approach"),
    text("last_run_at"),
    Column("yield_count", Integer),
    Column("attempts", Integer),
    text("cursor"),
    text("cache_until"),
    UniqueConstraint("owner_id", "query_hash"),
)
research_runs = table(
    "research_runs",
    text("command"),
    text("status"),
    text("started_at"),
    text("finished_at"),
    Column("requests", Integer),
    Column("observations", Integer),
    jsoncol("diagnostics"),
    jsoncol("checkpoint"),
)
raw_observations = table(
    "raw_observations",
    ref("source_id", "source_registry", False),
    text("source_item_id", False),
    text("url", False),
    text("normalized_url", False),
    text("published_at"),
    text("observed_at", False),
    text("title"),
    text("excerpt"),
    text("content_hash", False),
    text("author_hash"),
    text("access_status"),
    text("license"),
    jsoncol("provenance"),
    ref("run_id", "research_runs"),
    Column("synthetic", Boolean),
    Column("archived", Boolean),
    UniqueConstraint("owner_id", "source_id", "source_item_id"),
    UniqueConstraint("owner_id", "normalized_url"),
    UniqueConstraint("owner_id", "content_hash"),
)
problem_clusters = table(
    "problem_clusters",
    text("fingerprint", False),
    text("name"),
    text("job"),
    text("symptom"),
    text("root_cause"),
    text("buyer"),
    text("workaround"),
    Column("time_cost_minutes", Float),
    Column("independent_customers", Integer),
    jsoncol("unknowns"),
    UniqueConstraint("owner_id", "fingerprint"),
)
cluster_observations = table(
    "cluster_observations",
    ref("cluster_id", "problem_clusters", False),
    ref("observation_id", "raw_observations", False),
    UniqueConstraint("owner_id", "cluster_id", "observation_id"),
)
opportunities = table(
    "opportunities",
    ref("cluster_id", "problem_clusters"),
    text("title", False),
    text("problem"),
    text("solution"),
    text("buyer"),
    text("industry"),
    text("category"),
    text("geography"),
    text("language"),
    text("track"),
    text("status"),
    jsoncol("labels"),
    Column("favorite", Boolean),
    Column("pinned", Boolean),
    text("mvp"),
    jsoncol("distribution"),
    jsoncol("unknowns"),
    jsoncol("weaknesses"),
    text("analysis_method"),
    text("model_version"),
    text("prompt_version"),
    Column("synthetic", Boolean),
    Column("novelty", Float),
    Column("upside", Float),
    Column("confidence", Float),
    Column("effort", Float),
    Column("customer_validated", Boolean),
    ref("run_id", "research_runs"),
    text("replay_hash"),
    UniqueConstraint("owner_id", "replay_hash"),
)
opportunity_evidence = table(
    "opportunity_evidence",
    ref("opportunity_id", "opportunities", False),
    ref("observation_id", "raw_observations"),
    text("claim", False),
    text("claim_type", False),
    text("quote"),
    text("stance"),
    text("assessment"),
    UniqueConstraint("owner_id", "opportunity_id", "observation_id", "claim_type", "claim"),
)
competitors = table(
    "competitors",
    ref("opportunity_id", "opportunities", False),
    text("name", False),
    text("url"),
    text("features"),
    text("limitations"),
    ref("observation_id", "raw_observations"),
)
pricing_snapshots = table(
    "pricing_snapshots",
    ref("competitor_id", "competitors", False),
    Column("amount", Float),
    text("currency"),
    text("billing_period"),
    text("observed_at"),
    ref("observation_id", "raw_observations", False),
)
spending_signals = table(
    "spending_signals",
    ref("opportunity_id", "opportunities", False),
    ref("observation_id", "raw_observations", False),
    text("kind"),
    Column("amount", Float),
    text("currency"),
    text("claim_type"),
    text("excerpt"),
)
scores = table(
    "scores",
    ref("opportunity_id", "opportunities", False),
    jsoncol("dimensions"),
    Column("weighted_score", Float),
    Column("coverage", Float),
    text("version"),
    text("model_version"),
    jsoncol("evidence_ids"),
    text("assessed_at"),
    UniqueConstraint("owner_id", "opportunity_id"),
)
score_history = table(
    "score_history", ref("opportunity_id", "opportunities", False), jsoncol("snapshot"), text("event")
)
research_queue = table(
    "research_queue",
    ref("opportunity_id", "opportunities"),
    text("kind"),
    text("query", False),
    Column("priority", Integer),
    text("status"),
    text("due_at"),
    ref("run_id", "research_runs"),
    Column("attempts", Integer),
    text("last_error"),
)
validation_experiments = table(
    "validation_experiments",
    ref("opportunity_id", "opportunities", False),
    text("kind"),
    text("hypothesis"),
    text("success_criteria"),
    text("status"),
    text("result"),
    text("evidence_url"),
)
owner_feedback = table(
    "owner_feedback",
    ref("opportunity_id", "opportunities", False),
    text("kind"),
    text("note", False),
    text("evidence_url"),
    Column("genuine_buyer_feedback", Boolean),
)
provider_usage = table(
    "provider_usage",
    ref("source_id", "source_registry", False),
    ref("run_id", "research_runs"),
    text("request_id", False),
    text("month"),
    text("status"),
    Column("estimated_cost", Float),
    Column("actual_cost", Float),
    Column("units", Integer),
    Column("tokens", Integer),
    text("credit_type"),
    UniqueConstraint("owner_id", "request_id"),
)
budget_months = table(
    "budget_months",
    text("month", False),
    Column("spent", Float),
    Column("reserved", Float),
    Column("limit_usd", Float),
    Column("stop_usd", Float),
    UniqueConstraint("owner_id", "month"),
)
system_alerts = table(
    "system_alerts",
    text("severity"),
    text("code"),
    text("message"),
    ref("run_id", "research_runs"),
    Column("resolved", Boolean),
)
job_locks = table(
    "job_locks",
    text("name", False),
    text("holder", False),
    text("expires_at", False),
    UniqueConstraint("owner_id", "name"),
)

for t in metadata.tables.values():
    t.append_constraint(UniqueConstraint("owner_id", "id", name=f"uq_{t.name}_owner_id"))
    for column in t.c:
        for foreign in list(column.foreign_keys):
            target = foreign.target_fullname
            t.append_constraint(
                ForeignKeyConstraint(
                    ["owner_id", column.name],
                    [target.rsplit(".", 1)[0] + ".owner_id", target],
                    name=f"fk_{t.name}_{column.name}_owner",
                )
            )
    Index(f"ix_{t.name}_owner_updated", t.c.owner_id, t.c.updated_at)
Index("ix_raw_source_date", raw_observations.c.source_id, raw_observations.c.published_at)
Index("ix_queue_due", research_queue.c.owner_id, research_queue.c.status, research_queue.c.due_at)
Index(
    "ix_opportunity_filters",
    opportunities.c.owner_id,
    opportunities.c.track,
    opportunities.c.status,
    opportunities.c.industry,
    opportunities.c.buyer,
)

TABLES = metadata.tables
