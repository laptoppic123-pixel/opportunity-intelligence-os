# n8n on GitHub Actions

The selected architecture is **run a job, save its durable results, then stop**. GitHub hosts the job, so the laptop is not required during execution. This does not move or alter the existing laptop n8n installation.

## What is configured

- Manual-only `n8n batch runner` workflow on standard Ubuntu 24.04 runners; no schedules or push triggers.
- n8n 2.44.6, pinned to the official Linux amd64 Docker manifest digest. Registry availability was verified without starting local Docker.
- Runtime check for the n8n version, workflow-import command, and workflow-execution command. It does not execute an agent or connect to Supabase.
- A batch execution harness that accepts only names in `n8n/workflows/approved.json`. The manifest is deliberately empty until the AI agent is built and reviewed.
- Temporary SQLite storage inside the container. No existing n8n database, Docker volume, local network service, or Supabase administration credential is used.
- A 15-minute job limit, a 12-minute process limit, one batch job at a time, and container cleanup on success or failure.
- No exposed ports, Docker socket mount, n8n server, tunneling, persistent MCP endpoint, or retained workflow execution data.
- Runtime checking has no container network access. Future approved workflow execution can access APIs, but credentials are not provisioned yet.

## First runtime check

1. Confirm remaining included GitHub Actions capacity and spending controls at https://github.com/settings/billing/usage. The account's balance has not been verified by Codex; the workflow's confirmation checkbox is a manual gate, not an automatic billing check.
2. Open https://github.com/laptoppic123-pixel/opportunity-intelligence-os/actions/workflows/n8n-batch.yml.
3. Choose **Run workflow**, branch **main**, mode **runtime-check**, leave the workflow name empty, and confirm included allowance only after checking it.
4. The job should report PASS and stop. The check requires no API keys. It consumes runner minutes and downloads the pinned public n8n image. The first cloud run has already succeeded; repeating it is unnecessary unless the runtime configuration changes.

If the allowance confirmation is false, GitHub skips the batch job before allocating its runner. This gate applies to this batch workflow; the separate Phase 0 Supabase check is also manual and must only be dispatched after capacity is checked.

## Next phase: create the agent

Build and validate the new agent workflow separately; do not export or migrate unrelated existing workflows. Save reviewed workflow JSON under `n8n/workflows/`, with a stable ID, `active: false`, and a Manual Trigger. Add its reviewed filename and ID under a short name in `approved.json`, for example a future entry with `file` and `id` fields.

The harness imports and executes the workflow in the same temporary container, using `n8n import:workflow` followed by `n8n execute --id`. It never runs `n8n start`. Workflows requiring credentials are rejected until a credential provisioning design is approved and implemented. Do not hardcode keys in workflow parameters, exports, expressions, or Code nodes.

All durable business results must be saved to the dedicated Opportunity Intelligence OS Supabase project or another explicitly approved destination before the job exits. The temporary n8n database is not a business datastore. Supabase integration and agent credentials remain pending; they are not enabled by the runtime check.

GitHub Actions jobs do not supply a continuously available n8n editor or MCP connection. Codex can version code, dispatch approved jobs, and inspect their run status through GitHub. A visual n8n editor can still be used locally during authoring without making the laptop part of cloud execution.

## Verification and limits

Setup verification covers the pinned registry manifest, local harness validation and failure cleanup, committed file contents, GitHub workflow registration, and absence of automatic triggers. After the owner confirmed available included runner capacity, the first cloud runtime check succeeded: https://github.com/laptoppic123-pixel/opportunity-intelligence-os/actions/runs/40189280773. Its single Ubuntu job ran for about 65 seconds, with checkout, n8n CLI checks, and cleanup reporting success. No retry was needed. No business workflow, Supabase request, or AI provider was invoked.

Five local boundary tests passed: unknown workflows never invoke Docker; a missing allowance confirmation blocks cloud execution; a non-main branch blocks cloud execution; a timed-out run attempts cleanup of only its own container; and the runtime-check command has no container network, host storage mount, or exposed ports. Docker was mocked for those tests; the separate successful GitHub run establishes actual runtime execution. Importing and executing an agent workflow remains a later-phase test.

References:

- https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line.md
- https://github.com/n8n-io/n8n/releases/tag/n8n%402.44.6
- https://docs.github.com/en/actions/reference/limits
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
