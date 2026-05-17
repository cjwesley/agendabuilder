"""Pass 3: form editor — load, render, save round-trip."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

from app import AGENDAS_DIR, app, blank_issue, load_issue, save_issue_to_disk
from formparse import form_to_issue_dict, parse_path


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Work on a copy of the fixtures so tests don't mutate the repo.
    test_agendas = tmp_path / "agendas"
    shutil.copytree(Path(__file__).parent.parent / "agendas", test_agendas)
    monkeypatch.setattr("app.AGENDAS_DIR", test_agendas)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_parse_path_simple():
    assert parse_path("name") == ["name"]
    assert parse_path("a.b") == ["a", "b"]
    assert parse_path("headlines[0].figure") == ["headlines", 0, "figure"]
    assert parse_path("sections[2].items[1].name") == ["sections", 2, "items", 1, "name"]


def test_form_to_dict_lists():
    items = [
        ("headlines[0].figure", "3"),
        ("headlines[0].kicker", "Big"),
        ("headlines[1].figure", "18"),
        ("headlines[1].kicker", "Table"),
    ]
    d = form_to_issue_dict(items)
    assert d["headlines"][0] == {"figure": "3", "kicker": "Big"}
    assert d["headlines"][1] == {"figure": "18", "kicker": "Table"}


def test_form_to_dict_hidden_checkbox_pair():
    # Hidden default precedes the checkbox in DOM order; when checked, both
    # values submit and the checkbox wins (last-write semantics).
    # (Use index 0 since gaps are stripped — index 2 alone would collapse to 0.)
    items = [
        ("sections[0].minimal", "false"),
        ("sections[0].minimal", "true"),
    ]
    d = form_to_issue_dict(items)
    assert d["sections"][0]["minimal"] == "true"


def test_form_to_dict_gaps_are_stripped():
    # Real-world: when an item is removed client-side and the form submits
    # without that index, we collapse the list rather than insert a hole.
    items = [
        ("sections[0].name", "a"),
        ("sections[2].name", "c"),
    ]
    d = form_to_issue_dict(items)
    assert [s["name"] for s in d["sections"]] == ["a", "c"]


def test_editor_renders(client):
    resp = client.get("/edit/2026-02-10")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Issue 02 · February 10, 2026" in html
    assert 'name="headlines[0].figure"' in html
    assert 'name="sections[0].articles[0].headline"' in html
    # Preview iframe uses srcdoc with the inlined snapshot HTML
    assert 'id="preview-pane"' in html
    assert "srcdoc=" in html
    # Snapshot content is HTML-escaped inside the srcdoc attribute.
    assert "Issue 02 · February 10, 2026" in html


def test_save_roundtrip_preserves_value(client):
    # Load the editor, then POST a save that changes one value, then reload.
    editor = client.get("/edit/2026-05-12")
    assert editor.status_code == 200

    # Get the existing issue, serialize to form data, change one field, post it.
    issue = load_issue("2026-05-12")
    # Build a minimal form payload from issue to avoid duplicating template logic.
    payload = _issue_to_form_data(issue)

    # Mutate: change the first headline figure.
    for i, (k, _v) in enumerate(payload):
        if k == "headlines[0].figure":
            payload[i] = (k, "42")
            break

    resp = client.post("/save/2026-05-12", data=MultiDict(payload), follow_redirects=False)
    assert resp.status_code in (302, 200, 422), resp.data.decode()[:500]

    # Re-load and check the change persisted.
    reloaded = load_issue("2026-05-12")
    assert reloaded.headlines[0].figure == "42"


def test_save_validation_failure_returns_422(client):
    # Submit invalid data (a consent item name > 80 chars).
    issue = load_issue("2026-02-10")
    payload = _issue_to_form_data(issue)
    too_long = "x" * 200
    for i, (k, _v) in enumerate(payload):
        if k.startswith("sections[2].items[0].name"):  # consent section
            payload[i] = (k, too_long)
            break
    resp = client.post("/save/2026-02-10", data=MultiDict(payload), follow_redirects=False)
    assert resp.status_code == 422


def test_preview_returns_snapshot_html(client):
    issue = load_issue("2026-05-12")
    payload = _issue_to_form_data(issue)
    # Change subtitle to confirm preview reflects edits.
    for i, (k, _v) in enumerate(payload):
        if k == "masthead.subtitle":
            payload[i] = (k, "Edited subtitle for preview test.")
            break
    resp = client.post("/preview", data=MultiDict(payload))
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'id="preview-pane"' in body
    assert "Edited subtitle for preview test." in body
    # The disk YAML stays untouched (preview never writes).
    reloaded = load_issue("2026-05-12")
    assert "Edited subtitle for preview test." not in reloaded.masthead.subtitle


def test_preview_renders_error_on_invalid(client):
    # Empty body: no fields → validation will fail.
    resp = client.post("/preview", data={"issue_number": "1"})
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Validation error" in body
    assert 'id="preview-pane"' in body


def test_blank_issue_validates():
    from datetime import date as _d
    issue = blank_issue(_d(2026, 6, 9))
    assert issue.issue_number == 1
    assert len(issue.headlines) == 3
    # Round-trip through YAML
    AGENDAS_DIR.mkdir(parents=True, exist_ok=True)
    p = save_issue_to_disk(issue)
    try:
        assert p.exists()
        back = load_issue("2026-06-09")
        assert back.meeting_date == issue.meeting_date
    finally:
        if p.exists():
            p.unlink()


# ---------- helpers ----------

def _issue_to_form_data(issue):
    """Convert an Issue back into form data items in the same shape the editor
    would submit. Mirrors templates/partials/form_section.html field names.
    """
    items: list[tuple[str, str]] = [
        ("issue_number", str(issue.issue_number)),
        ("meeting_date", issue.meeting_date.isoformat()),
        ("masthead.subtitle", issue.masthead.subtitle),
        ("masthead.meta.convening", issue.masthead.meta.convening),
        ("masthead.meta.where", issue.masthead.meta.where),
        ("masthead.meta.how_to_join_html", issue.masthead.meta.how_to_join_html),
    ]
    for i, h in enumerate(issue.headlines):
        items += [
            (f"headlines[{i}].kicker", h.kicker),
            (f"headlines[{i}].figure", h.figure),
            (f"headlines[{i}].caption", h.caption),
        ]
    for si, sec in enumerate(issue.sections):
        p = f"sections[{si}]"
        items.append((f"{p}.kind", sec.kind))
        items.append((f"{p}.title", sec.title))
        if sec.kind != "consent" and getattr(sec, "eyebrow", None) is not None:
            items.append((f"{p}.eyebrow", sec.eyebrow or ""))
        if sec.kind == "feature":
            for ai, a in enumerate(sec.articles):
                ap = f"{p}.articles[{ai}]"
                items += [
                    (f"{ap}.tag", a.tag),
                    (f"{ap}.headline", a.headline),
                    (f"{ap}.body_md", a.body_md),
                ]
                for li, lid in enumerate(a.legistar_ids):
                    items.append((f"{ap}.legistar_ids[{li}]", lid))
                if a.pullquote:
                    items += [
                        (f"{ap}.pullquote.label", a.pullquote.label),
                        (f"{ap}.pullquote.text", a.pullquote.text),
                    ]
        elif sec.kind == "study":
            for ii, it in enumerate(sec.items):
                ip = f"{p}.items[{ii}]"
                items += [
                    (f"{ip}.tag", it.tag),
                    (f"{ip}.headline", it.headline),
                    (f"{ip}.body", it.body),
                ]
                for li, lid in enumerate(it.legistar_ids):
                    items.append((f"{ip}.legistar_ids[{li}]", lid))
        elif sec.kind == "regular_compact":
            for ii, it in enumerate(sec.items):
                ip = f"{p}.items[{ii}]"
                items += [
                    (f"{ip}.tag", it.tag),
                    (f"{ip}.name", it.name),
                    (f"{ip}.text", it.text),
                ]
                for li, lid in enumerate(it.legistar_ids):
                    items.append((f"{ip}.legistar_ids[{li}]", lid))
        elif sec.kind == "consent":
            items.append((f"{p}.minimal", "false"))
            if sec.minimal:
                items.append((f"{p}.minimal", "true"))
            items.append((f"{p}.summary", sec.summary))
            for ii, it in enumerate(sec.items):
                ip = f"{p}.items[{ii}]"
                items.append((f"{ip}.flag", "false"))
                if it.flag:
                    items.append((f"{ip}.flag", "true"))
                items += [
                    (f"{ip}.legistar_id", it.legistar_id),
                    (f"{ip}.name", it.name),
                    (f"{ip}.why", it.why),
                ]
        elif sec.kind == "civic_notes":
            for bi, b in enumerate(sec.blocks):
                bp = f"{p}.blocks[{bi}]"
                items += [(f"{bp}.kind", b.kind), (f"{bp}.label", b.label)]
                if b.kind == "proclamations":
                    for pi, pr in enumerate(b.items):
                        pp = f"{bp}.items[{pi}]"
                        items += [(f"{pp}.name", pr.name), (f"{pp}.when", pr.when)]
                elif b.kind == "body":
                    items.append((f"{bp}.side", "false"))
                    if b.side:
                        items.append((f"{bp}.side", "true"))
                    items += [
                        (f"{bp}.legistar_id", b.legistar_id),
                        (f"{bp}.body_html", b.body_html),
                    ]

    items += [
        ("footer.meeting_details.date_short", issue.footer.meeting_details.date_short),
        ("footer.meeting_details.time", issue.footer.meeting_details.time),
        ("footer.meeting_details.location", issue.footer.meeting_details.location),
        ("footer.public_comment_html", issue.footer.public_comment_html),
        ("footer.editor_note_html", issue.footer.editor_note_html),
    ]
    return items
