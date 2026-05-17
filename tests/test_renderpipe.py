"""Pass 5: HTML + PNG export pipeline."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app import app, load_issue
from render import _discover_chromium, write_html


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setattr("app.OUT_DIR", out)
    return out


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_agendas = tmp_path / "agendas"
    shutil.copytree(Path(__file__).parent.parent / "agendas", test_agendas)
    test_out = tmp_path / "out"
    monkeypatch.setattr("app.AGENDAS_DIR", test_agendas)
    monkeypatch.setattr("app.OUT_DIR", test_out)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_write_html_produces_full_snapshot(out_dir):
    with app.app_context(), app.test_request_context():
        issue = load_issue("2026-05-12")
        html_path = write_html(issue, out_dir)
    assert html_path.exists()
    content = html_path.read_text()
    assert "Issue 03 · May 12, 2026" in content
    assert "Three Study Sessions" in content
    assert "<!DOCTYPE html>" in content
    # Full standalone document
    assert "</html>" in content


def test_render_export_html_only_when_no_browser(client, monkeypatch):
    # Force the "browser missing" path by monkeypatching the playwright launch
    # to raise. This validates the 207 partial-success response shape.
    import render

    def boom(*a, **kw):
        raise RuntimeError("no chromium for you")

    monkeypatch.setattr(render, "write_png", boom)

    resp = client.post("/render/2026-05-12")
    assert resp.status_code == 207, resp.data
    body = resp.get_json()
    assert body["html"].endswith("2026-05-12.html")
    assert body["png"] is None
    assert "no chromium" in body["error"]


def test_serve_out_returns_html_file(client):
    # First, ensure an HTML render lands in the (overridden) out dir.
    import render

    # Disable PNG to keep this test browser-free.
    def html_only(issue, out_dir):
        return render.write_html(issue, out_dir), render.write_html(issue, out_dir)

    # Just hit the partial path via a launch failure path.
    import app as appmod

    def force_png_fail(*a, **kw):
        raise RuntimeError("png disabled for test")

    import pytest as _pt
    with _pt.MonkeyPatch.context() as mp:
        mp.setattr(render, "write_png", force_png_fail)
        first = client.post("/render/2026-05-12")
    assert first.status_code == 207

    # Now the HTML file should be servable.
    resp = client.get("/out/2026-05-12.html")
    assert resp.status_code == 200
    assert "Issue 03 · May 12, 2026".encode("utf-8") in resp.data


@pytest.mark.skipif(
    _discover_chromium() is None and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
    reason="No Playwright Chromium discoverable; set PLAYWRIGHT_BROWSERS_PATH to enable",
)
def test_full_png_render(client):
    resp = client.post("/render/2026-05-12")
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["png"].endswith("2026-05-12.png")
    # Fetch the PNG itself
    img = client.get(body["png"])
    assert img.status_code == 200
    assert img.data[:8] == b"\x89PNG\r\n\x1a\n"
    # Sanity: at viewport 1080 × 2 DPR full-page, expect at least ~100KB
    assert len(img.data) > 100_000
