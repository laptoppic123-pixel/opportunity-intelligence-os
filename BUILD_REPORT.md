# BUILD verification — V2.0

Status: **READY_FOR_CREDENTIALS**. The final package specification supersedes Phase 0 plans.

- 18 Python application modules; 21 relational tables; 3 checked-in unapplied PostgreSQL migrations.
- 10 local Streamlit pages and working research views, queue actions, notes, favorites, comparisons, manual entry/import, validation records and exports.
- Explicit synthetic fixture demo: 6 ideas, digital/physical tracks separated; no actual buyer feedback or live demand implied.
- Genuine 12-sheet XLSX plus CSV and Markdown from one snapshot. An independent Excel reader opened the workbook, verified six Ideas rows and six source hyperlinks, and recognized UTC date/time cells.
- 24 focused offline tests passed, including an explicit unexpected-charge circuit-breaker test. Ruff syntax/error checks and staged-file whitespace checks passed.
- HTTP access is forbidden by the offline test fixture. Tests cover missing credentials, exact dedupe/provenance, owner/FK integrity, favorite persistence, nullable scores, physical separation, synthetic validation exclusion, leases, budget stops, unknown price/credit denial, injection boundaries, model fallback/source validation, export agreement, migration/RLS defaults, inactive schedules, all dashboard pages and queue persistence, backup integrity/restore gates, and fixture-only source parsers.
- The demo server is localhost-only. No public website, paid host or always-online n8n dependency was introduced.
- Active Actions definitions are manual only. Cron definitions are stored as `.disabled` and have not been activated. No GitHub Actions job was dispatched for this V2 build.
- No source-research API, model catalog/inference, paid service, production database mutation or migration was run during BUILD. Provider documentation and dependency packages were read to implement interfaces; this is not live research validation.

Live PostgreSQL/RLS/RPC tests, actual provider availability/prices, external quotas, a bounded real ingestion, optional free-model analysis, database–dashboard–XLSX reconciliation, cost/failover tests and scheduler activation are reserved for phase 3 after credentials and explicit owner authorization. No source is claimed live-verified.

Connection sequence and exact variable names: CONNECTION_CHECKLIST.md.
