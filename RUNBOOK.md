# Operator runbook

## Build state and activation boundary

Live access, paid APIs and scheduled research remain disabled. Basic offline checks may be repeated locally; do not dispatch cloud jobs merely to repeat them. No application production migrations or live source/model calls were made during BUILD. The earlier 65-second n8n runtime proof is not a Python research integration test.

After credentials and explicit authorization: apply the three reviewed migrations to the dedicated Supabase project; check tables, grants, RLS and RPCs; enable live/activation for one bounded test with paid mode OFF; run `oi --live doctor`, one capped discovery, optional free-model analysis, real DB-to-dashboard-to-Excel reconciliation and budget/failover tests. Report actual counts/costs and missing optional capabilities. Only then activate the schedule template.

## Scheduled operation (opt-in)

`research-scheduled.yml.disabled` is inert. After successful phase-3 checks run `uv run python scripts/activate_schedules.py --confirm-activation` locally, review/push the resulting `.yml`, then set `OI_SCHEDULES_ENABLED=true` in repository Variables. It also requires `OI_ACTIVATED` and `OI_LIVE_ENABLED`. The UTC definitions are discovery 01:17/07:17/13:17/19:17; analysis daily 03:41; weekly report/private backup Sunday 04:53. Actions may delay or miss cron events: the next authorized run uses persisted source-specific cursors and due research tasks. Do not create a second scheduled workflow to compensate.

All worker jobs share `opportunity-os-global-worker` concurrency and a database lease. Jobs time out after 12 minutes; source loops cap at 10 requests, 30 observations and 180 seconds by default. Leases expire after 900 seconds if a process is terminated. A killed queue task marked running can be returned to pending in the dashboard after the lease expires. Outputs/checkpoints remain in Supabase; completed jobs need no laptop.

Disable schedules by setting `OI_SCHEDULES_ENABLED=false` and removing/renaming the active scheduler file. Disable all live access with `OI_LIVE_ENABLED=false`; paid mode remains independently OFF. Do not change unrelated projects.

## Source health, retries and quota handling

Check Source/API Health and System notices. A provider with no key, unreviewed terms, unknown price, exhausted quota, required backoff or three consecutive failures is skipped. HTTP 429/502/503/504 have bounded backoff; explicit retry-after is persisted. Stack Exchange backoff is honored. No scraping, new-account rotation, alternative identity or trial-reset workaround is implemented. Review the actual issue before resetting a circuit. `configs/sources.yaml` owns enablement; adding a key does not enable an optional provider.

No responding source means an explicit diagnostic and zero live discoveries, never replacement synthetic results. Cursors advance only for sources that succeeded. The query cache, source identity and replay hashes protect against duplicate work. A source excerpt's `root_cause` or time cost is populated only when explicitly extractable; query-target buyer labels are not confirmed buyer identities.

## Models, credits and budgets

After authorized catalog refresh, select actual role IDs and record current prices; catalogs expire after 24 hours. Leave unneeded roles blank. Unsupported schemas, invalid source IDs/quotes and failed providers fall back to another configured authorized provider, otherwise rules-only. Independent critique must use a different model/provider identity. Refreshing catalogs is itself a bounded authorized network action.

The owner has explicitly authorized finite allowances in `configs/sources.yaml`: Tavily 1,000 basic-search credits and Exa a conservative $19 cap against approximately $20 promotional credit. These are owner declarations, not provider-verified balances. No balance API polling or automatic renewal is performed. Each Tavily attempt holds one credit; each bounded Exa search holds $0.02 even when settlement reports less. Failed or unknown costs cannot restore credit headroom. The existing atomic reservation RPC enforces these source caps across workers. Changing an API key does not reset usage. A fixed local expiry stops use until another explicit declaration. Exa promotional use is distinct from unrestricted paid access; `OI_PAID_ENABLED` stays false. Other nonzero-priced providers retain the paid gate. No code enables top-ups, upgrades, purchases or vendor billing changes. The aggregate monthly stop remains an additional guard. Usage denominated in dollars can consume promotional credit and is not evidence of a card charge.

## Retention, backup and restore

Retention clears stale low-value excerpts and copied quotes after `OI_RETENTION_DAYS` (90 by default), retaining source URLs, hashes and provenance. Favorite/pinned evidence is protected. Review these exceptions against the 500 MB free-database budget and archive/export owner favorites when necessary. Snapshots refuse more than 50,000 rows per table instead of silently truncating.

Backups are timestamp/versioned encrypted objects in **private** `oi-private-backups` Storage. Generate and securely preserve `OI_BACKUP_ENCRYPTION_KEY` separately. `oi --live backup --upload` creates/verifies the bucket after activation. No public download links are produced. The weekly backup job is disabled until scheduler activation. Keep a bounded backup history: review monthly, retain the most recent eight weekly backups and any intentional restore point; delete older encrypted objects via the owner dashboard/Storage console after verifying a recent restore. No destructive Storage cleanup runs automatically during BUILD.

To restore, download an encrypted object privately. Run `oi restore PATH` with the same owner and encryption key; inspect schema version, checksum and counts. Restore to an empty/reviewed dedicated recovery project first, explicitly updating `OI_EXPECTED_PROJECT_REF` and URL; never a DMS database. Authorize `oi --live restore PATH --apply --confirm-owner UUID`. Upserts are idempotent and do not wipe existing tables. Check foreign keys, counts, source links and exports. Key loss makes encrypted backups unrecoverable.

## Security and limitations

Run Streamlit only at 127.0.0.1. Do not deploy it publicly or share service keys. `.env`, local demo data and exports are ignored. Never copy production credentials into fixture files, source text or download buttons. Logs expose health/status and redacted errors rather than response bodies. A local dashboard with a service key is for the trusted owner, not untrusted users. Exa/Tavily do not replace source access permissions. Regulatory/financial information is a research signal, not professional advice.

Physical products remain an optional separate track with unknown economics until fulfillment/shipping/returns are assessed; unsafe/illegal/age-restricted sectors are excluded. Public commentary does not constitute direct buyer validation. A genuine interview, commitment or pilot must be recorded as owner feedback. No outreach is sent automatically.

## Useful diagnosis

- `uv run oi doctor`: offline presence/flags only; never echoes secrets.
- `uv run oi --live doctor`: authorized Supabase table/RPC connection test after migrations.
- `uv run pytest`: focused offline checks; HTTP transport is blocked in the test fixture.
- `uv run ruff check src dashboard scripts tests`: syntax/error checks.
- `uv run oi --demo export`: independent synthetic records only; never production validation.

If a live operation fails, stop schedules, inspect source health and redacted alerts, preserve checkpoints, and rerun only the affected bounded operation after fixing the cause. No recovery path purchases credits, changes accounts, weakens TLS/RLS or resets trials.


## OpenRouter reliability and deferred analysis

Preferred role models remain first. The official `openrouter/free` router is an automatic fallback for model-specific unavailability; the previously configured fallback is retained when applicable. A fresh catalog must show zero prices for the free router. Requests keep the zero provider-price ceiling; the returned underlying model must also match a zero-priced catalog entry. Independent criticism cannot reuse that underlying generating model. Local parsing and canonical evidence validation run before any AI label is written. An incomplete response is deferred, even if the HTTP status is 200.

Retry-After is persisted for both seconds and HTTP-date values and blocks OpenRouter-wide fallback until it expires. Account-wide daily free exhaustion suspends all OpenRouter models until the provider reset or the next UTC day, whichever is later. Other account-wide limits pause the provider; model-specific upstream failures pause the affected route. No balance APIs or key rotation are used to bypass these limits. There are no same-model retry loops. Transient circuits expire automatically; credential/access or cost anomalies still require review.

Unfinished work is saved idempotently in the existing `research_queue` with kinds `ai_fast`, `ai_deep` or `ai_critic`. The opportunity and original evidence remain intact, and failed AI never becomes an AI-validated or customer-validated result. Normal research searches exclude these AI tasks. The next **authorized** discover/analyze/deep-dive worker resumes at most one due AI job, within the same request/time/lease limits. Pending tasks survive interruption, and the same task is not retried again in that worker. Automatic schedules remain OFF; this queue creates no timer or background process. Once schedules are explicitly approved, existing scheduled worker commands will use the same resumption path.

The focused live router check returned HTTP 200 at zero reported cost, but its response reached the output token limit. It was rejected and queued; the previous assessment remained unchanged. Status: **RESEARCH READY / AI DEGRADED**. No migrations or prior integration suite were repeated. See the dated reliability report for the detailed test evidence.


## Final activation handoff

The final optimization uses one opportunity and at most three relevant 450-character excerpts per AI request. A 621-character instruction/JSON blueprint replaces the full schema sent to providers. The compact wire response contains solution/MVP hypotheses, short weaknesses/unknowns and 1-2 exact evidence quotations. Canonical source-ID, quote, scoring and duplicate-key checks still run locally before applying an assessment; the opportunity ID is bound to the single canonical input. Existing full-format responses remain compatible.

Generation limits are sent only for advertised parameters: normally 1536 tokens, or up to 3072 for reasoning-capable routes, reduced by any advertised provider completion cap. Mandatory reasoning uses an advertised low effort; unsupported controls are omitted. Research continues and AI work remains queued on errors, limits or incomplete responses.

The only prepared automatic triggers are four daily scans, daily analysis, and weekly reporting/backup. The standard Linux runner is eligible for free compute while this owner-approved repository remains public. The account billing API returned 404, so account-wide remaining minutes are not asserted. No Actions job was started. The template remains `.disabled`, all activation variables remain false, and scheduled paid mode is hard-coded false.

Database, local Streamlit production view and canonical 12-sheet Excel generation passed connection spot-checks. The existing private backup bucket was prepared and an encrypted storage probe was uploaded, read and deleted. No schema migration was run. The single final compact AI request returned HTTP 429 and was deferred without changing the previous assessment. No additional live retry is required before activating normal research: AI is optional and resumes from the queue in authorized workers. Approval to enable the existing schedule is the remaining operational handoff.
