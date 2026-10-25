-- Opportunity Intelligence OS V2. Generated schema. No seed data or production writes during BUILD.
BEGIN;


CREATE TABLE IF NOT EXISTS budget_months (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	month TEXT NOT NULL,
	spent FLOAT,
	reserved FLOAT,
	limit_usd FLOAT,
	stop_usd FLOAT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, month),
	CONSTRAINT uq_budget_months_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_budget_months_owner_updated ON budget_months (owner_id, updated_at);

ALTER TABLE public.budget_months ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_months FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.budget_months FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.budget_months TO service_role;


CREATE TABLE IF NOT EXISTS job_locks (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	name TEXT NOT NULL,
	holder TEXT NOT NULL,
	expires_at TEXT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, name),
	CONSTRAINT uq_job_locks_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_job_locks_owner_updated ON job_locks (owner_id, updated_at);

ALTER TABLE public.job_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_locks FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.job_locks FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.job_locks TO service_role;


CREATE TABLE IF NOT EXISTS problem_clusters (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	fingerprint TEXT NOT NULL,
	name TEXT,
	job TEXT,
	symptom TEXT,
	root_cause TEXT,
	buyer TEXT,
	workaround TEXT,
	time_cost_minutes FLOAT,
	independent_customers INTEGER,
	unknowns JSON,
	PRIMARY KEY (id),
	UNIQUE (owner_id, fingerprint),
	CONSTRAINT uq_problem_clusters_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_problem_clusters_owner_updated ON problem_clusters (owner_id, updated_at);

ALTER TABLE public.problem_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.problem_clusters FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.problem_clusters FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.problem_clusters TO service_role;


CREATE TABLE IF NOT EXISTS queries (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	query_hash TEXT NOT NULL,
	text TEXT NOT NULL,
	dimensions JSON,
	approach TEXT,
	last_run_at TEXT,
	yield_count INTEGER,
	attempts INTEGER,
	cursor TEXT,
	cache_until TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, query_hash),
	CONSTRAINT uq_queries_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_queries_owner_updated ON queries (owner_id, updated_at);

ALTER TABLE public.queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.queries FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.queries FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.queries TO service_role;


CREATE TABLE IF NOT EXISTS research_runs (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	command TEXT,
	status TEXT,
	started_at TEXT,
	finished_at TEXT,
	requests INTEGER,
	observations INTEGER,
	diagnostics JSON,
	checkpoint JSON,
	PRIMARY KEY (id),
	CONSTRAINT uq_research_runs_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_research_runs_owner_updated ON research_runs (owner_id, updated_at);

ALTER TABLE public.research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_runs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.research_runs FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.research_runs TO service_role;


CREATE TABLE IF NOT EXISTS source_registry (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	name TEXT NOT NULL,
	enabled BOOLEAN,
	credentials_present BOOLEAN,
	current_terms_checked BOOLEAN,
	capabilities JSON,
	estimated_cost FLOAT,
	daily_quota INTEGER,
	monthly_quota INTEGER,
	reset_date TEXT,
	failure_count INTEGER,
	last_success TEXT,
	last_error TEXT,
	added_information_value FLOAT,
	priority INTEGER,
	legal_access_notes TEXT,
	config JSON,
	PRIMARY KEY (id),
	UNIQUE (owner_id, name),
	CONSTRAINT uq_source_registry_owner_id UNIQUE (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_source_registry_owner_updated ON source_registry (owner_id, updated_at);

ALTER TABLE public.source_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_registry FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.source_registry FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.source_registry TO service_role;


CREATE TABLE IF NOT EXISTS opportunities (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	cluster_id VARCHAR(100),
	title TEXT NOT NULL,
	problem TEXT,
	solution TEXT,
	buyer TEXT,
	industry TEXT,
	category TEXT,
	geography TEXT,
	language TEXT,
	track TEXT,
	status TEXT,
	labels JSON,
	favorite BOOLEAN,
	pinned BOOLEAN,
	mvp TEXT,
	distribution JSON,
	unknowns JSON,
	weaknesses JSON,
	analysis_method TEXT,
	model_version TEXT,
	prompt_version TEXT,
	synthetic BOOLEAN,
	novelty FLOAT,
	upside FLOAT,
	confidence FLOAT,
	effort FLOAT,
	customer_validated BOOLEAN,
	run_id VARCHAR(100),
	replay_hash TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, replay_hash),
	FOREIGN KEY(cluster_id) REFERENCES problem_clusters (id),
	FOREIGN KEY(run_id) REFERENCES research_runs (id),
	CONSTRAINT uq_opportunities_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_opportunities_cluster_id_owner FOREIGN KEY(owner_id, cluster_id) REFERENCES problem_clusters (owner_id, id),
	CONSTRAINT fk_opportunities_run_id_owner FOREIGN KEY(owner_id, run_id) REFERENCES research_runs (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_opportunities_owner_updated ON opportunities (owner_id, updated_at);

CREATE INDEX IF NOT EXISTS ix_opportunity_filters ON opportunities (owner_id, track, status, industry, buyer);

ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunities FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.opportunities FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.opportunities TO service_role;


CREATE TABLE IF NOT EXISTS provider_usage (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	source_id VARCHAR(100) NOT NULL,
	run_id VARCHAR(100),
	request_id TEXT NOT NULL,
	month TEXT,
	status TEXT,
	estimated_cost FLOAT,
	actual_cost FLOAT,
	units INTEGER,
	tokens INTEGER,
	credit_type TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, request_id),
	FOREIGN KEY(source_id) REFERENCES source_registry (id),
	FOREIGN KEY(run_id) REFERENCES research_runs (id),
	CONSTRAINT uq_provider_usage_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_provider_usage_source_id_owner FOREIGN KEY(owner_id, source_id) REFERENCES source_registry (owner_id, id),
	CONSTRAINT fk_provider_usage_run_id_owner FOREIGN KEY(owner_id, run_id) REFERENCES research_runs (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_provider_usage_owner_updated ON provider_usage (owner_id, updated_at);

ALTER TABLE public.provider_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_usage FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.provider_usage FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.provider_usage TO service_role;


CREATE TABLE IF NOT EXISTS raw_observations (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	source_id VARCHAR(100) NOT NULL,
	source_item_id TEXT NOT NULL,
	url TEXT NOT NULL,
	normalized_url TEXT NOT NULL,
	published_at TEXT,
	observed_at TEXT NOT NULL,
	title TEXT,
	excerpt TEXT,
	content_hash TEXT NOT NULL,
	author_hash TEXT,
	access_status TEXT,
	license TEXT,
	provenance JSON,
	run_id VARCHAR(100),
	synthetic BOOLEAN,
	archived BOOLEAN,
	PRIMARY KEY (id),
	UNIQUE (owner_id, source_id, source_item_id),
	UNIQUE (owner_id, normalized_url),
	UNIQUE (owner_id, content_hash),
	FOREIGN KEY(source_id) REFERENCES source_registry (id),
	FOREIGN KEY(run_id) REFERENCES research_runs (id),
	CONSTRAINT uq_raw_observations_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_raw_observations_source_id_owner FOREIGN KEY(owner_id, source_id) REFERENCES source_registry (owner_id, id),
	CONSTRAINT fk_raw_observations_run_id_owner FOREIGN KEY(owner_id, run_id) REFERENCES research_runs (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_raw_source_date ON raw_observations (source_id, published_at);

CREATE INDEX IF NOT EXISTS ix_raw_observations_owner_updated ON raw_observations (owner_id, updated_at);

ALTER TABLE public.raw_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.raw_observations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.raw_observations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.raw_observations TO service_role;


CREATE TABLE IF NOT EXISTS source_quotas (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	source_id VARCHAR(100) NOT NULL,
	period TEXT NOT NULL,
	used INTEGER,
	limit_value INTEGER,
	reset_at TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, source_id, period),
	FOREIGN KEY(source_id) REFERENCES source_registry (id),
	CONSTRAINT uq_source_quotas_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_source_quotas_source_id_owner FOREIGN KEY(owner_id, source_id) REFERENCES source_registry (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_source_quotas_owner_updated ON source_quotas (owner_id, updated_at);

ALTER TABLE public.source_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_quotas FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.source_quotas FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.source_quotas TO service_role;


CREATE TABLE IF NOT EXISTS system_alerts (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	severity TEXT,
	code TEXT,
	message TEXT,
	run_id VARCHAR(100),
	resolved BOOLEAN,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES research_runs (id),
	CONSTRAINT uq_system_alerts_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_system_alerts_run_id_owner FOREIGN KEY(owner_id, run_id) REFERENCES research_runs (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_system_alerts_owner_updated ON system_alerts (owner_id, updated_at);

ALTER TABLE public.system_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_alerts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.system_alerts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.system_alerts TO service_role;


CREATE TABLE IF NOT EXISTS cluster_observations (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	cluster_id VARCHAR(100) NOT NULL,
	observation_id VARCHAR(100) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, cluster_id, observation_id),
	FOREIGN KEY(cluster_id) REFERENCES problem_clusters (id),
	FOREIGN KEY(observation_id) REFERENCES raw_observations (id),
	CONSTRAINT uq_cluster_observations_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_cluster_observations_cluster_id_owner FOREIGN KEY(owner_id, cluster_id) REFERENCES problem_clusters (owner_id, id),
	CONSTRAINT fk_cluster_observations_observation_id_owner FOREIGN KEY(owner_id, observation_id) REFERENCES raw_observations (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_cluster_observations_owner_updated ON cluster_observations (owner_id, updated_at);

ALTER TABLE public.cluster_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cluster_observations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.cluster_observations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.cluster_observations TO service_role;


CREATE TABLE IF NOT EXISTS competitors (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	name TEXT NOT NULL,
	url TEXT,
	features TEXT,
	limitations TEXT,
	observation_id VARCHAR(100),
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(observation_id) REFERENCES raw_observations (id),
	CONSTRAINT uq_competitors_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_competitors_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id),
	CONSTRAINT fk_competitors_observation_id_owner FOREIGN KEY(owner_id, observation_id) REFERENCES raw_observations (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_competitors_owner_updated ON competitors (owner_id, updated_at);

ALTER TABLE public.competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.competitors FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.competitors FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.competitors TO service_role;


CREATE TABLE IF NOT EXISTS opportunity_evidence (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	observation_id VARCHAR(100),
	claim TEXT NOT NULL,
	claim_type TEXT NOT NULL,
	quote TEXT,
	stance TEXT,
	assessment TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, opportunity_id, observation_id, claim_type, claim),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(observation_id) REFERENCES raw_observations (id),
	CONSTRAINT uq_opportunity_evidence_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_opportunity_evidence_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id),
	CONSTRAINT fk_opportunity_evidence_observation_id_owner FOREIGN KEY(owner_id, observation_id) REFERENCES raw_observations (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_opportunity_evidence_owner_updated ON opportunity_evidence (owner_id, updated_at);

ALTER TABLE public.opportunity_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunity_evidence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.opportunity_evidence FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.opportunity_evidence TO service_role;


CREATE TABLE IF NOT EXISTS owner_feedback (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	kind TEXT,
	note TEXT NOT NULL,
	evidence_url TEXT,
	genuine_buyer_feedback BOOLEAN,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	CONSTRAINT uq_owner_feedback_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_owner_feedback_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_owner_feedback_owner_updated ON owner_feedback (owner_id, updated_at);

ALTER TABLE public.owner_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.owner_feedback FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.owner_feedback FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.owner_feedback TO service_role;


CREATE TABLE IF NOT EXISTS research_queue (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100),
	kind TEXT,
	query TEXT NOT NULL,
	priority INTEGER,
	status TEXT,
	due_at TEXT,
	run_id VARCHAR(100),
	attempts INTEGER,
	last_error TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(run_id) REFERENCES research_runs (id),
	CONSTRAINT uq_research_queue_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_research_queue_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id),
	CONSTRAINT fk_research_queue_run_id_owner FOREIGN KEY(owner_id, run_id) REFERENCES research_runs (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_research_queue_owner_updated ON research_queue (owner_id, updated_at);

CREATE INDEX IF NOT EXISTS ix_queue_due ON research_queue (owner_id, status, due_at);

ALTER TABLE public.research_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_queue FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.research_queue FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.research_queue TO service_role;


CREATE TABLE IF NOT EXISTS score_history (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	snapshot JSON,
	event TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	CONSTRAINT uq_score_history_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_score_history_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_score_history_owner_updated ON score_history (owner_id, updated_at);

ALTER TABLE public.score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.score_history FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.score_history FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.score_history TO service_role;


CREATE TABLE IF NOT EXISTS scores (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	dimensions JSON,
	weighted_score FLOAT,
	coverage FLOAT,
	version TEXT,
	model_version TEXT,
	evidence_ids JSON,
	assessed_at TEXT,
	PRIMARY KEY (id),
	UNIQUE (owner_id, opportunity_id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	CONSTRAINT uq_scores_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_scores_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_scores_owner_updated ON scores (owner_id, updated_at);

ALTER TABLE public.scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scores FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scores FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.scores TO service_role;


CREATE TABLE IF NOT EXISTS spending_signals (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	observation_id VARCHAR(100) NOT NULL,
	kind TEXT,
	amount FLOAT,
	currency TEXT,
	claim_type TEXT,
	excerpt TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(observation_id) REFERENCES raw_observations (id),
	CONSTRAINT uq_spending_signals_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_spending_signals_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id),
	CONSTRAINT fk_spending_signals_observation_id_owner FOREIGN KEY(owner_id, observation_id) REFERENCES raw_observations (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_spending_signals_owner_updated ON spending_signals (owner_id, updated_at);

ALTER TABLE public.spending_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spending_signals FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.spending_signals FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.spending_signals TO service_role;


CREATE TABLE IF NOT EXISTS validation_experiments (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	opportunity_id VARCHAR(100) NOT NULL,
	kind TEXT,
	hypothesis TEXT,
	success_criteria TEXT,
	status TEXT,
	result TEXT,
	evidence_url TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	CONSTRAINT uq_validation_experiments_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_validation_experiments_opportunity_id_owner FOREIGN KEY(owner_id, opportunity_id) REFERENCES opportunities (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_validation_experiments_owner_updated ON validation_experiments (owner_id, updated_at);

ALTER TABLE public.validation_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.validation_experiments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.validation_experiments FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.validation_experiments TO service_role;


CREATE TABLE IF NOT EXISTS pricing_snapshots (
	id VARCHAR(100) NOT NULL,
	owner_id VARCHAR(36) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	updated_at VARCHAR(40) NOT NULL,
	competitor_id VARCHAR(100) NOT NULL,
	amount FLOAT,
	currency TEXT,
	billing_period TEXT,
	observed_at TEXT,
	observation_id VARCHAR(100) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(competitor_id) REFERENCES competitors (id),
	FOREIGN KEY(observation_id) REFERENCES raw_observations (id),
	CONSTRAINT uq_pricing_snapshots_owner_id UNIQUE (owner_id, id),
	CONSTRAINT fk_pricing_snapshots_competitor_id_owner FOREIGN KEY(owner_id, competitor_id) REFERENCES competitors (owner_id, id),
	CONSTRAINT fk_pricing_snapshots_observation_id_owner FOREIGN KEY(owner_id, observation_id) REFERENCES raw_observations (owner_id, id)
)

;

CREATE INDEX IF NOT EXISTS ix_pricing_snapshots_owner_updated ON pricing_snapshots (owner_id, updated_at);

ALTER TABLE public.pricing_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pricing_snapshots FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pricing_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pricing_snapshots TO service_role;

-- No anon/authenticated policies: access is denied. Only the trusted server key accesses data.
COMMIT;
