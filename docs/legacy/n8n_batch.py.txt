"""Run the pinned n8n CLI in a disposable Docker container; never start a server."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    config = json.loads((ROOT / "n8n/runtime.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"docker\.n8n\.io/n8nio/n8n:[0-9.]+@sha256:[a-f0-9]{64}", config["image"]):
        raise ValueError("n8n must use an official image pinned by digest.")
    if config["platform"] != "linux/amd64":
        raise ValueError("This runner is configured for Linux amd64.")
    return config


def approved_workflow(name):
    allowed = json.loads((ROOT / "n8n/workflows/approved.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name) or name not in allowed:
        raise ValueError("No approved workflow matches this name. Agent workflows have not been added yet.")
    item = allowed[name]
    base = (ROOT / "n8n/workflows").resolve()
    path = (base / item["file"]).resolve()
    if not path.is_relative_to(base) or path.suffix != ".json" or path.name == "approved.json":
        raise ValueError("Workflow file must stay inside n8n/workflows.")
    workflow = json.loads(path.read_text(encoding="utf-8"))
    identifier = workflow.get("id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier != item.get("id"):
        raise ValueError("Workflow ID must match the approved manifest.")
    if workflow.get("active") is not False:
        raise ValueError("Batch workflow exports must explicitly set active=false.")
    nodes = workflow.get("nodes", [])
    if not nodes or not any(node.get("type") == "n8n-nodes-base.manualTrigger" for node in nodes):
        raise ValueError("Batch execution requires a Manual Trigger workflow.")
    if any(node.get("credentials") for node in nodes):
        raise ValueError("Credential-backed execution needs a separately approved credential provisioning step.")
    return path, identifier


def container_command(mode, workflow_name=""):
    config = configuration()
    selected = approved_workflow(workflow_name) if mode == "execute" else None
    name = "opportunity-n8n-" + uuid.uuid4().hex[:16]
    command = [
        "docker", "run", "--rm", "--name", name,
        "--platform", config["platform"], "--user", "1000:1000",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--cpus", "1", "--memory", "1536m", "--pids-limit", "256",
        "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=256m",
        "--tmpfs", "/home/node/.n8n:rw,nosuid,nodev,mode=0700,uid=1000,gid=1000,size=256m",
        "--env", "N8N_DIAGNOSTICS_ENABLED=false",
        "--env", "N8N_VERSION_NOTIFICATIONS_ENABLED=false",
        "--env", "N8N_TEMPLATES_ENABLED=false",
        "--env", "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true",
        "--env", "GENERIC_TIMEZONE=" + config["timezone"],
        "--env", "TZ=" + config["timezone"],
        "--env", "DB_TYPE=sqlite",
        "--env", "EXECUTIONS_DATA_SAVE_ON_SUCCESS=none",
        "--env", "EXECUTIONS_DATA_SAVE_ON_ERROR=none",
    ]
    if selected:
        path, identifier = selected
        command += [
            "--network", "bridge",
            "--mount", "type=bind,src=" + str(path.parent) + ",dst=/input,readonly",
            "--env", "BATCH_WORKFLOW_FILE=" + path.name,
            "--env", "BATCH_WORKFLOW_ID=" + identifier,
        ]
        shell = 'n8n import:workflow --input="/input/$BATCH_WORKFLOW_FILE" && n8n execute --id="$BATCH_WORKFLOW_ID"'
    else:
        command += ["--network", "none"]
        shell = "n8n --version && n8n import:workflow --help && n8n execute --help"
    command += ["--entrypoint", "/bin/sh", config["image"], "-ec", shell]
    return name, command


def run(mode, workflow_name="", dry_run=False):
    name, command = container_command(mode, workflow_name)
    if dry_run:
        print(json.dumps({"mode": mode, "command": command, "executes_docker": False}, indent=2))
        return
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("BATCH_ALLOWANCE_CONFIRMED") != "true":
            raise ValueError("Verify included runner allowance before starting this job.")
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise ValueError("Cloud batch execution is restricted to the main branch.")
    print("Starting disposable n8n container for " + mode + ".", flush=True)
    try:
        # Keep workflow data and n8n diagnostic output out of GitHub logs.
        subprocess.run(command, check=True, timeout=720, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("PASS: " + mode + " completed.", flush=True)
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=False, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Disposable container cleanup attempted.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["runtime-check", "execute"])
    parser.add_argument("--workflow", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(args.mode, args.workflow, args.dry_run)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Do not print command output or workflow contents.
        if isinstance(error, ValueError):
            print("ERROR: " + str(error), file=sys.stderr)
        else:
            print("ERROR: n8n runtime failed (" + type(error).__name__ + "). No automatic retry was attempted.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
