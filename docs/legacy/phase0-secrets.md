# Repository secret preparation

Target repository: `laptoppic123-pixel/opportunity-intelligence-os`, **Private**.

Open **Settings > Secrets and variables > Actions > New repository secret** in the existing private repository:

https://github.com/laptoppic123-pixel/opportunity-intelligence-os/settings/secrets/actions

| Name | Required now | Source and purpose |
| --- | --- | --- |
| `SUPABASE_URL` | Yes, for the manual connectivity check | Project URL: `https://vaxesikpcgrdxzqikyur.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Yes, for the manual connectivity check | The dedicated project's enabled modern publishable key; use the project's API Keys settings |
| `SUPABASE_SECRET_KEY` | No; reserved for a later approved backend phase | Dedicated project server-side key. Bypasses RLS; never use in browser code or commit it |

The Phase 0 check uses only the URL and publishable key. No privileged key is needed to test that the Auth and REST services accept the project's API key. It does not verify application-table permissions or perform database writes.

Do not copy credentials from another project. Do not send secret values in chat. Empty placeholder secrets were not created, and no secret values were retrieved or committed during this preparation.

An administrative `SUPABASE_ACCESS_TOKEN` and `SUPABASE_DB_PASSWORD` are not required for this check. Revisit deployment credentials and minimum permissions only if migration automation is approved later.

Use repository secrets in a job's environment with `${{ secrets.SUPABASE_URL }}` and `${{ secrets.SUPABASE_PUBLISHABLE_KEY }}`. Keep logs free of credentials and response bodies. The supplied workflow rejects any URL other than the verified project URL and refuses redirects.

References:

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- https://supabase.com/docs/guides/getting-started/api-keys
