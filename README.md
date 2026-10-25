# Opportunity Intelligence OS · V2.0

Evidence-grounded discovery of unmet business needs, niche software opportunities, automation services and digital products. **BUILD is ready for credentials. Live research, paid APIs and schedules are OFF.** This is not a promise of demand, validation or profit.

## Start the offline application (Windows PowerShell)

```powershell
git clone https://github.com/laptoppic123-pixel/opportunity-intelligence-os.git
cd opportunity-intelligence-os
py -m pip install uv==0.9.8
uv sync --locked --extra dev
uv run oi doctor
uv run oi demo
$env:OI_DEMO_MODE = 'true'
uv run streamlit run dashboard/app.py --server.address 127.0.0.1
```

Open http://127.0.0.1:8501. The six fixtures are visibly **DEMO / SYNTHETIC DATA**, including fictional `example.com` evidence links. No live sources or models run in demo mode. Local SQLite is used only for this explicit demo/test mode; the production worker has no SQLite fallback.

```powershell
uv run oi --demo analyze
uv run oi --demo export --output .local/demo-exports
uv run pytest
uv run ruff check src dashboard scripts tests
```

The export contains 12 genuine Excel sheets, one CSV per view, and a Markdown research summary from one database snapshot. Excel is an export, not another datastore.

## What is implemented

- Python 3.12 batch worker: query planning, source rotation, checkpointed ingestion, exact/near-copy deduplication, candidate problem clustering, nullable assessed scoring, rules-only reasoning, optional grounded LLM batches, skeptical research queue, spending and competitor-price extraction.
- Keyless-first HN Algolia, official HN, public GitHub Issues and Stack Exchange adapters; reviewed RSS/vendor changelogs; optional Exa, Tavily, Serper, YouTube metadata, OpenAlex and a field-mapped procurement JSON adapter. Restricted Reddit/G2 access stays OFF.
- Provider registry with capabilities, missing-key skips, terms flags, quotas, yield, circuit breakers and cost reservations. OpenRouter is the initial optional model gateway; a configurable OpenAI-compatible Haimaker fallback is implemented without inventing its endpoint or model catalog.
- 21 owner-scoped relational tables, PostgreSQL security migrations, atomic leases, quota/budget RPCs and consistent snapshot export. Supabase is the only production source of truth.
- Ten working local Streamlit pages, manual hypotheses/import, favorites, notes, validation experiments, queue controls, source health and usage, evidence links, side-by-side comparison and exports.
- Private encrypted versioned backups and gated restore, retention of low-value excerpts, manual worker Actions, and an inactive schedule template.

## Production connection (later)

Follow [CONNECTION_CHECKLIST.md](CONNECTION_CHECKLIST.md), then explicitly authorize phase 3. The already-created dedicated project is `vaxesikpcgrdxzqikyur` in the **Ai agent** organization. Do not connect any DMS or existing n8n database.

Production uses the Supabase REST API from trusted Python processes. `SUPABASE_SECRET_KEY` is server-only. Tables deny access to `anon` and `authenticated`; the local owner dashboard accesses them through its Python server. `OI_OWNER_ID` is a stable generated UUID namespace, not an email or an assumed Supabase Auth user. URL protection defaults to the dedicated project reference.

To return from a demo PowerShell session before production: `Remove-Item Env:OI_DEMO_MODE`; configure `.env` without committing it. Live access requires **both** `OI_ACTIVATED=true` and `OI_LIVE_ENABLED=true`, plus an explicit CLI `--live` for worker execution. Paid mode has a separate flag and stays OFF.

## Commands

| Command | Purpose |
| --- | --- |
| `oi doctor` | Missing-key-safe, offline configuration report; never echoes secrets |
| `oi demo` | Explicitly create/reuse synthetic SQLite fixtures |
| `oi --demo analyze` | Exercise the real rules pipeline offline |
| `oi --demo export --output PATH` | Snapshot-consistent XLSX/CSV/Markdown |
| `oi --live discover` | Bounded, checkpointed public-source collection after activation |
| `oi --live analyze` | Rules-only analysis; optional configured model batch |
| `oi --live enrich` | Extract cited spend/price references from observed evidence |
| `oi --live challenge` | Queue skeptical research; optional independent critic |
| `oi --live deep-dive` | Bounded discovery, deeper analysis and enrichment |
| `oi --live models --refresh` | Fetch permitted model IDs/prices after authorization; presets are empty |
| `oi --live report` | Generate current canonical reports |
| `oi --live backup --upload` | Encrypted backup into a verified private Storage bucket |
| `oi restore PATH` | Integrity/owner check, dry-run by default |
| `oi --live restore PATH --apply --confirm-owner UUID` | Explicit, idempotent owner-scoped restore |

## Execution and cost controls

GitHub Actions is a batch executor, not an always-online n8n server. V2 supersedes the earlier n8n runtime experiment; its manual workflow definitions are archived under `docs/legacy/` and are not application dependencies. No original laptop workflow is migrated.

All active workflows are manual only. `.github/workflows/research-scheduled.yml.disabled` is ignored by GitHub. It defines four daily discovery runs at off-hour UTC minutes, daily analysis, twice-weekly deep dives, and weekly reports/backups. It can be activated only after phase-3 checks; it also requires three opt-in repository variables. GitHub concurrency and a database lease prevent overlap. Cursors are tracked per query/source, failed sources do not advance, and the initial catch-up window is bounded to seven days.

External paid requests default to $0. The configurable monthly ceiling is $20 and the internal paid stop is $19; unknown prices/credits are refused. Internal estimates cannot guarantee vendor billing. Configure vendor-side caps and GitHub spending limits. Read [RUNBOOK.md](RUNBOOK.md).

## Validation boundary

BUILD checks are offline unit tests, fixture-based UI checks, SQL inspection and export structure/consistency checks. Live research endpoints, models, PostgreSQL migrations, production RLS, cloud business jobs and real database-to-dashboard-to-XLSX consistency are deliberately **not claimed verified**. They belong to phase 3 after credentials and explicit activation.

See [ARCHITECTURE.md](ARCHITECTURE.md), [RUNBOOK.md](RUNBOOK.md) and the checked-in V2 specification in `docs/specification/`.
