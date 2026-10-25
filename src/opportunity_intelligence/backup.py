from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
import httpx
from cryptography.fernet import Fernet
from .safety import redact
from .schema import TABLES


def backup(store, path=None, *, upload=False):
    key = os.getenv("OI_BACKUP_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError("Set a private OI_BACKUP_ENCRYPTION_KEY before backup; never commit it")
    rows = store.snapshot()
    payload = json.dumps(
        {"schema_version": 2, "owner_id": store.owner, "tables": rows}, sort_keys=True
    ).encode()
    envelope = json.dumps(
        {"sha256": hashlib.sha256(payload).hexdigest(), "payload": payload.decode()}
    ).encode()
    blob = Fernet(key.encode()).encrypt(gzip.compress(envelope))
    name = datetime.now(timezone.utc).strftime("%Y/%m/%d/") + str(uuid4()) + ".json.gz.enc"
    if upload:
        store.settings.require_live()
        base = store.settings.supabase_url.rstrip("/") + "/storage/v1"
        headers = {
            "apikey": store.settings.secret_key,
            "Authorization": "Bearer " + store.settings.secret_key,
        }
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            # Creating the private bucket is an explicit activated backup action, never a BUILD migration.
            response = client.post(
                base + "/bucket",
                headers=headers,
                json={"id": "oi-private-backups", "name": "oi-private-backups", "public": False},
            )
            if response.status_code not in {200, 201, 400, 409}:
                raise RuntimeError("Private backup bucket could not be prepared")
            bucket = client.get(base + "/bucket/oi-private-backups", headers=headers)
            if bucket.status_code != 200 or bucket.json().get("public") is not False:
                raise PermissionError("Backup bucket must be private")
            response = client.post(
                base + "/object/oi-private-backups/" + store.owner + "/" + name,
                headers={**headers, "Content-Type": "application/octet-stream", "x-upsert": "false"},
                content=blob,
            )
            if response.status_code not in {200, 201}:
                raise RuntimeError("Encrypted backup upload failed")
        return {"private_object": store.owner + "/" + name, "bytes": len(blob), "schema_version": 2}
    if path is None:
        raise ValueError("Choose a private local backup path")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return {"path": str(path), "bytes": len(blob), "schema_version": 2}


def restore(store, path, *, apply=False, confirm_owner=None):
    key = os.getenv("OI_BACKUP_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError("Backup decryption key required")
    envelope = json.loads(gzip.decompress(Fernet(key.encode()).decrypt(Path(path).read_bytes())))
    payload = envelope["payload"].encode()
    if hashlib.sha256(payload).hexdigest() != envelope["sha256"]:
        raise ValueError("Backup integrity failure")
    data = json.loads(payload)
    if data["schema_version"] != 2 or data["owner_id"] != store.owner:
        raise ValueError("Backup schema/owner mismatch")
    if apply and confirm_owner != store.owner:
        raise PermissionError("Explicit matching owner confirmation required")
    counts = {name: len(rows) for name, rows in data["tables"].items()}
    if apply:
        if not store.settings.demo:
            store.settings.require_live()
        with store.lease():
            for t in TABLES.values():
                if t.name == "job_locks":
                    continue
                for row in data["tables"].get(t.name, []):
                    if row.get("owner_id") != store.owner:
                        raise ValueError("Cross-owner row rejected")
                    store.upsert(t.name, row)
    return {"dry_run": not apply, "counts": counts}
