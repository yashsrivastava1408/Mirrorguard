"""The tenants, keys and retention commands."""

import pytest

from mirrorguard.cli import main
from mirrorguard.config import get_settings


@pytest.fixture
def cli_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MG_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_tenant_and_key_commands(cli_database, capsys):
    assert main(["tenants", "create", "acme", "--name", "Acme Ltd"]) == 0
    assert main(["tenants", "create", "acme"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["tenants", "list"]) == 0
    assert "Acme Ltd" in capsys.readouterr().out

    assert main(["keys", "create", "acme", "--role", "reviewer", "--name", "asha"]) == 0
    out = capsys.readouterr().out
    key_id = out.split("Key id : ")[1].split()[0]
    assert "API key: mg_" in out and "not shown again" in out
    assert main(["keys", "create", "ghost"]) == 1
    capsys.readouterr()

    assert main(["keys", "list", "acme"]) == 0
    listing = capsys.readouterr().out
    assert "reviewer" in listing and "active" in listing
    assert main(["keys", "revoke", "acme", key_id]) == 0
    assert main(["keys", "revoke", "acme", key_id]) == 1
    capsys.readouterr()
    assert main(["keys", "list", "acme"]) == 0
    assert "revoked" in capsys.readouterr().out


def test_retention_command(cli_database, capsys):
    assert main(["retention", "purge", "--days", "30"]) == 0
    assert "Removed 0 guardrail events older than 30 days" in capsys.readouterr().out
    assert main(["retention", "purge"]) == 0
    assert "older than 90 days" in capsys.readouterr().out
    assert main(["retention", "purge", "--days", "0"]) == 1
