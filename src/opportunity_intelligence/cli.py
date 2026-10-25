import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from .config import Settings, ROOT
from .safety import redact


def doctor(settings, *, live=False):
    result = {
        "phase": "READY_FOR_CREDENTIALS",
        "demo": settings.demo,
        "live_enabled": settings.live,
        "activated": settings.activated,
        "paid_enabled": settings.paid,
        "supabase_url_present": bool(settings.supabase_url),
        "supabase_server_key_present": bool(settings.secret_key),
        "owner_id_present": bool(settings.owner),
        "monthly_limit_usd": str(settings.monthly_limit),
        "internal_paid_stop_usd": str(settings.paid_stop),
        "migrations_present": len(list((ROOT / "db/migrations").glob("*.sql"))),
        "network_checked": False,
        "optional_keys": {
            name: bool(os.getenv(name))
            for name in [
                "OPENROUTER_API_KEY",
                "HAIMAKER_API_KEY",
                "EXA_API_KEY",
                "TAVILY_API_KEY",
                "SOURCE_GITHUB_TOKEN",
                "STACKEXCHANGE_KEY",
            ]
        },
    }
    if live:
        settings.require_live()
        from .store import Store

        store = Store(settings)
        for name in ("source_registry", "opportunities", "job_locks", "budget_months"):
            store.list(name, limit=1)
        # Verify atomic RPC existence with a short-lived private lease, not a business write.
        with store.lease("doctor", seconds=30):
            pass
        result.update(phase="CONNECTION_CHECKED", network_checked=True)
    return result


def main():
    parser = argparse.ArgumentParser(
        prog="oi", description="Opportunity Intelligence OS V2. Live and paid operations are OFF by default."
    )
    parser.add_argument(
        "--demo", action="store_true", help="Explicit synthetic SQLite mode; no external requests"
    )
    parser.add_argument(
        "--live", action="store_true", help="Explicitly authorize a bounded operation AFTER activation"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in [
        "doctor",
        "demo",
        "discover",
        "analyze",
        "enrich",
        "challenge",
        "deep-dive",
        "report",
        "models",
        "backup",
        "restore",
        "retention",
    ]:
        p = commands.add_parser(name)
        if name in {"report", "backup"}:
            p.add_argument("--output", default=str(ROOT / ".local/exports"))
        if name == "backup":
            p.add_argument("--upload", action="store_true")
        if name == "restore":
            p.add_argument("path")
            p.add_argument("--apply", action="store_true")
            p.add_argument("--confirm-owner")
        if name == "models":
            p.add_argument("--refresh", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("--output", default=str(ROOT / ".local/exports"))
    args = parser.parse_args()
    cfg = Settings.load(demo=True if args.demo or args.command == "demo" else None)
    try:
        if args.command == "doctor":
            result = doctor(cfg, live=args.live)
        else:
            from .store import Store
            from .providers import ProviderRegistry

            store = Store(cfg)
            if cfg.demo:
                from .demo import seed_demo

                seed_demo(store)
            if args.command == "demo":
                result = {
                    "mode": "DEMO / SYNTHETIC DATA",
                    "database": str(cfg.data_dir / "demo.sqlite3"),
                    "ideas": len(store.all("opportunities")),
                }
            elif args.command in {"discover", "analyze", "enrich", "challenge", "deep-dive"}:
                from .orchestrator import run

                result = run(store, args.command, live=args.live)
            elif args.command in {"report", "export"}:
                from .exports import export_all

                result = export_all(store, args.output)
            elif args.command == "models":
                from .transport import Transport
                from .models import ModelRouter

                if args.refresh:
                    if not args.live:
                        raise PermissionError("Catalog refresh requires explicit --live after activation")
                    cfg.require_live()
                    ProviderRegistry(store).sync()
                    t = Transport(store)
                    try:
                        result = {}
                        for source in store.all("source_registry"):
                            if source["config"].get("kind") == "model" and not t.registry.reason(source, 0):
                                result[source["name"]] = ModelRouter(t).refresh_catalog(source)
                    finally:
                        t.close()
                else:
                    result = {
                        "status": "No catalog network call made",
                        "instruction": "After activation: oi --live models --refresh; select exact returned IDs/prices.",
                    }
            elif args.command == "backup":
                from .backup import backup

                if args.upload and not args.live:
                    raise PermissionError("Upload requires --live")
                result = backup(store, Path(args.output) / "backup.json.gz.enc", upload=args.upload)
            elif args.command == "restore":
                from .backup import restore

                if args.apply and not cfg.demo and not args.live:
                    raise PermissionError("Restore requires --live")
                result = restore(store, args.path, apply=args.apply, confirm_owner=args.confirm_owner)
            elif args.command == "retention":
                if not cfg.demo and not args.live:
                    raise PermissionError("Retention requires --live")
                from .orchestrator import retain

                result = {"archived": retain(store)}
        print(json.dumps(redact(result), indent=2, default=str))
        return 0
    except (PermissionError, ValueError, RuntimeError, OSError) as exc:
        print(
            json.dumps({"status": "blocked", "reason": redact(str(exc)), "live_integration_verified": False})
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
