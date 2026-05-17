"""Pass 8: basic auth + healthz."""

from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest


def _b64(user: str, pw: str) -> str:
    return base64.b64encode(f"{user}:{pw}".encode()).decode()


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    test_agendas = tmp_path / "agendas"
    shutil.copytree(Path(__file__).parent.parent / "agendas", test_agendas)
    monkeypatch.setenv("BASIC_AUTH_USER", "cory")
    monkeypatch.setenv("BASIC_AUTH_PASS", "hunter2")
    # Re-import to pick up new env vars.
    import importlib

    import app
    importlib.reload(app)
    monkeypatch.setattr(app, "AGENDAS_DIR", test_agendas)
    app.app.config["TESTING"] = True
    with app.app.test_client() as c:
        yield c
    # Cleanup: reload app once more so leftover env doesn't bleed.
    import os
    os.environ.pop("BASIC_AUTH_USER", None)
    os.environ.pop("BASIC_AUTH_PASS", None)
    importlib.reload(app)


def test_healthz_is_unauthenticated(authed_client):
    resp = authed_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_unauthenticated_returns_401(authed_client):
    resp = authed_client.get("/2026-05-12")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert "Basic" in resp.headers["WWW-Authenticate"]


def test_wrong_credentials_returns_401(authed_client):
    resp = authed_client.get(
        "/2026-05-12",
        headers={"Authorization": "Basic " + _b64("cory", "wrong")},
    )
    assert resp.status_code == 401


def test_correct_credentials_works(authed_client):
    resp = authed_client.get(
        "/2026-05-12",
        headers={"Authorization": "Basic " + _b64("cory", "hunter2")},
    )
    assert resp.status_code == 200
    assert "Issue 03 · May 12, 2026" in resp.data.decode()


def test_no_credentials_configured_is_open(tmp_path, monkeypatch):
    """Local-dev mode: no env vars → no auth."""
    test_agendas = tmp_path / "agendas"
    shutil.copytree(Path(__file__).parent.parent / "agendas", test_agendas)
    monkeypatch.delenv("BASIC_AUTH_USER", raising=False)
    monkeypatch.delenv("BASIC_AUTH_PASS", raising=False)
    import importlib

    import app
    importlib.reload(app)
    monkeypatch.setattr(app, "AGENDAS_DIR", test_agendas)
    app.app.config["TESTING"] = True
    with app.app.test_client() as c:
        resp = c.get("/2026-05-12")
    assert resp.status_code == 200
