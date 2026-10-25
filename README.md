# Opportunity Intelligence OS

Phase 0 connection preparation only. The agent, data pipeline, dashboard, and schedules have not been built.

## Platform destinations

| Platform | Destination | Verified status |
| --- | --- | --- |
| GitHub | `laptoppic123-pixel/opportunity-intelligence-os` (private) | Created; authenticated CLI has admin and write access |
| GitHub Actions | Enabled; default workflow token is read-only | Execution held pending free-allowance verification |
| Supabase organization | `Ai agent` (`jmdhivmkjvukuvduojeg`) | Free plan; MCP access verified |
| Supabase project | `opportunity-intelligence-os` (`vaxesikpcgrdxzqikyur`) | Created; ACTIVE_HEALTHY; read-only SQL passed |
| Supabase region | `ap-south-1` | Verified |
| Streamlit | Local dashboard | Future phase; no account needed |

Project dashboard: https://supabase.com/dashboard/project/vaxesikpcgrdxzqikyur

The project was created under the approved Ai agent connection after a quote of $0/month. Its public schema is empty. No existing project or n8n workflow was changed.

## Connection setup remaining

1. Verify the account's remaining included runner allowance and spending controls before dispatching a run. The billing endpoint requires the additional `user` OAuth scope, which was not requested. Alternatively, the account owner can verify the allowance directly in GitHub Billing.
2. Add the Phase 0 repository secrets listed in `docs/secrets.md` directly in GitHub's secret settings. The Supabase publishable-key lookup did not return during preparation; no credential values were retrieved or installed.
3. Dispatch the connection check only after the included allowance is verified. Record its result before calling GitHub-to-Supabase connectivity verified.

Repository: https://github.com/laptoppic123-pixel/opportunity-intelligence-os

The account owner authorized GitHub CLI with `repo` and `workflow` scopes. Authenticated API checks verify repository administration and read/write access. Actions is enabled; default workflow token permissions are read-only and workflow approval of pull requests is disabled. The supplied check is manual only; uploading it does not trigger execution.

The GitHub connector separately authenticates the correct identity but exposes no app installations. GitHub CLI is the verified working repository connection; an additional connector installation is optional if future work specifically needs connector-based repository access.

The GitHub Free plan includes 2,000 standard runner minutes per month shared across the account's private repositories; this is an entitlement, not a verified remaining balance. Source: https://docs.github.com/en/billing/concepts/product-billing/github-actions

## n8n observation

The local MCP entry points to `http://localhost:5678/mcp-server/http`, but that address and `/healthz` both refused connections during preparation. No n8n tools were available in this chat. A duplicate `n8n-2` configuration appears to contain an entire `codex mcp add` command instead of an executable definition. It was not changed. The Supabase account used by existing n8n workflows remains unverified.

## Boundaries

No application tables, migrations, AI agent, paid features, recurring triggers, or dashboard were created. All existing DMS, n8n, and other Supabase resources were left untouched. GitHub stores code and runs bounded automation jobs; it is not a persistent n8n server or Streamlit hosting service.
