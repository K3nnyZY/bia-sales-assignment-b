"""Production guards and credential handling, without a database or provider."""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from test_deployment import production_settings

from app.deployment import bootstrap as module


@pytest.mark.parametrize(
    "name", ["app.seed", "app.runtime.seed", "app.governance.seed", "app.knowledge.seed"]
)
def test_original_development_seed_entrypoints_remain_blocked_in_production(name, monkeypatch):
    target = importlib.import_module(name)
    monkeypatch.setattr(target, "Settings", production_settings)
    monkeypatch.setattr(sys, "argv", [name])
    with pytest.raises(SystemExit):
        target.main()


def test_generator_creates_private_random_access_without_database_credentials(tmp_path):
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/railway_credentials.py"),
            "--access-only",
            "--directory",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    credentials = json.loads((tmp_path / "railway-credentials.json").read_text())
    manifest = json.loads((tmp_path / "railway-manifest.json").read_text())
    assert not (tmp_path / "railway-secrets.json").exists()
    assert len({row["token"] for row in credentials.values()}) == 7
    for role, data in credentials.items():
        assert data["token"].startswith("bia_") and len(data["token"]) >= 47
        assert data["token"] not in result.stdout
        assert "token" not in manifest[role]
        assert manifest[role]["role"] == ("viewer" if role == "customer-b" else role)
    for path in tmp_path.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    again = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/railway_credentials.py"),
            "--access-only",
            "--directory",
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
    )
    assert again.returncode != 0
    assert json.loads((tmp_path / "railway-credentials.json").read_text()) == credentials


def test_wrong_plaintext_manifest_is_not_exposed_in_cli_errors(tmp_path, monkeypatch):
    sensitive = "secret-should-not-appear-in-errors"
    manifest = {role: {"token": sensitive} for role in module.ROLES}
    path = tmp_path / "wrong-manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "Settings", production_settings)
    monkeypatch.setattr(module, "build_engine", lambda _: MagicMock())
    monkeypatch.setattr(
        sys,
        "argv",
        ["bootstrap", "provision-identities", "--confirm-synthetic-demo", "--manifest", str(path)],
    )
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert sensitive not in str(caught.value)
    assert "hash-only" in str(caught.value)
