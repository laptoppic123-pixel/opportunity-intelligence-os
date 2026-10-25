from cryptography.fernet import Fernet
import pytest
from opportunity_intelligence.backup import backup, restore
from opportunity_intelligence.demo import seed_demo


def test_encrypted_backup_integrity_and_restore_gate(store, tmp_path, monkeypatch):
    seed_demo(store)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("OI_BACKUP_ENCRYPTION_KEY", key)
    path = tmp_path / "private.enc"
    backup(store, path)
    assert b"Synthetic:" not in path.read_bytes()
    result = restore(store, path)
    assert result["dry_run"] and result["counts"]["opportunities"] == 6
    with pytest.raises(PermissionError):
        restore(store, path, apply=True, confirm_owner="wrong")
    restore(store, path, apply=True, confirm_owner=store.owner)
    assert len(store.all("opportunities")) == 6
