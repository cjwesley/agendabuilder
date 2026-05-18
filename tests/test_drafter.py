"""Pass 7: AI drafting — schema shape, system-prompt assembly, route plumbing.

The Anthropic SDK is mocked; we don't make real API calls here.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _drafter_module():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import drafter
    return drafter


def test_system_blocks_have_cache_marker_on_last():
    drafter = _drafter_module()
    blocks = drafter._system_blocks("feature")
    assert len(blocks) == 2
    # Voice guide first (no cache marker), task instructions second (with marker)
    assert "cache_control" not in blocks[0]
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    # Voice guide content present
    assert "Voice guide" in blocks[0]["text"]
    # Task-specific instructions present
    assert "Feature article" in blocks[1]["text"]


def test_system_blocks_per_kind():
    drafter = _drafter_module()
    for kind, sentinel in [("feature", "Feature"), ("study", "Study"), ("compact", "compact")]:
        blocks = drafter._system_blocks(kind)
        assert any(sentinel.lower() in b["text"].lower() for b in blocks), kind


def test_render_seed_includes_all_fields():
    drafter = _drafter_module()
    seed = {
        "title": "Foo Bar — escrow waiver",
        "legistar_ids": ["RES 26-198"],
        "matter_type": "Resolution",
        "agenda_section": "Regular Agenda",
        "staff_report_excerpt": "The escrow requirement applies to all units…",
        "overview": "A waiver request from the cohousing project.",
    }
    rendered = drafter._render_seed(seed)
    assert "Foo Bar" in rendered
    assert "RES 26-198" in rendered
    assert "Resolution" in rendered
    assert "Regular Agenda" in rendered
    assert "escrow requirement" in rendered
    assert "cohousing project" in rendered


def test_render_seed_handles_empty():
    drafter = _drafter_module()
    assert "best-effort" in drafter._render_seed({})


def test_draft_feature_calls_parse_with_expected_shape(monkeypatch):
    drafter = _drafter_module()

    # Build a fake response that messages.parse() would return
    fake_resp = MagicMock()
    fake_resp.parsed_output = drafter.FeatureDraft(
        headline="Headline.", tag="Tag", body_md="Body.",
        pullquote_label="", pullquote_text="",
    )
    fake_resp.usage = MagicMock(
        input_tokens=100, output_tokens=200,
        cache_read_input_tokens=0, cache_creation_input_tokens=80,
    )

    fake_client = MagicMock()
    fake_client.messages.parse.return_value = fake_resp
    drafter._client.cache_clear()
    monkeypatch.setattr(drafter, "_client", lambda: fake_client)

    out = drafter.draft_feature({"title": "T", "legistar_ids": ["RES 1"]})
    assert out.headline == "Headline."
    assert out.tag == "Tag"

    # Confirm the call shape
    kwargs = fake_client.messages.parse.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"]["effort"] == "high"
    assert kwargs["output_format"] is drafter.FeatureDraft
    # System is a list of cacheable text blocks; last one has cache_control
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_draft_compact_uses_medium_effort(monkeypatch):
    drafter = _drafter_module()
    fake_resp = MagicMock()
    fake_resp.parsed_output = drafter.CompactDraft(text="A short editorial frame.")
    fake_resp.usage = MagicMock(
        input_tokens=50, output_tokens=20,
        cache_read_input_tokens=0, cache_creation_input_tokens=40,
    )
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = fake_resp
    drafter._client.cache_clear()
    monkeypatch.setattr(drafter, "_client", lambda: fake_client)

    drafter.draft_compact({"title": "X"})
    kwargs = fake_client.messages.parse.call_args.kwargs
    assert kwargs["output_config"]["effort"] == "medium"
    assert kwargs["output_format"] is drafter.CompactDraft


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_agendas = tmp_path / "agendas"
    shutil.copytree(Path(__file__).parent.parent / "agendas", test_agendas)
    monkeypatch.setattr("app.AGENDAS_DIR", test_agendas)
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_route_feature_returns_drafted_json(client, monkeypatch):
    drafter = _drafter_module()
    fake = drafter.FeatureDraft(
        headline="Test headline about Madison Street.",
        tag="Housing on Madison",
        body_md="**1106 Madison** is the address.",
        pullquote_label="From the staff overview",
        pullquote_text="Two ordinances land together.",
    )
    monkeypatch.setattr(drafter, "draft_feature", lambda seed: fake)
    import app as appmod
    monkeypatch.setattr(appmod, "drafter", drafter)

    resp = client.post(
        "/draft/feature",
        json={"date": "2026-02-10", "section_idx": 0, "article_idx": 0},
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["headline"] == "Test headline about Madison Street."
    assert body["pullquote_label"] == "From the staff overview"


def test_route_returns_clear_error_when_no_api_key(client, monkeypatch):
    drafter = _drafter_module()

    def boom(seed):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    monkeypatch.setattr(drafter, "draft_feature", boom)
    import app as appmod
    monkeypatch.setattr(appmod, "drafter", drafter)

    resp = client.post(
        "/draft/feature",
        json={"date": "2026-02-10", "section_idx": 0, "article_idx": 0},
    )
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.get_json()["error"]


def test_route_400_on_bad_locators(client):
    resp = client.post("/draft/feature", json={"date": "2026-02-10"})
    assert resp.status_code == 400


def test_route_accepts_direct_seed(client, monkeypatch):
    drafter = _drafter_module()
    fake = drafter.CompactDraft(text="One-sentence frame.")
    monkeypatch.setattr(drafter, "draft_compact", lambda seed: fake)
    import app as appmod
    monkeypatch.setattr(appmod, "drafter", drafter)

    resp = client.post("/draft/compact", json={"seed": {"title": "Anything"}})
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "One-sentence frame."
