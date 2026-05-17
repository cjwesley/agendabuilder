from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from pydantic import ValidationError

from formparse import form_to_issue_dict
from legistar import (
    _cached_client,
    event_summary,
    find_board_body_id,
    import_event,
    list_events,
)
from render import install_filters, render_both, write_html
from schema import (
    CivicNotesSection,
    ConsentSection,
    FooterMeetingDetails,
    FooterStrip,
    Headline,
    Issue,
    Masthead,
    MetaRow,
    RegularCompactSection,
    StudySection,
)

AGENDAS_DIR = Path(__file__).parent / "agendas"
OUT_DIR = Path(__file__).parent / "out"

app = Flask(__name__)
install_filters(app.jinja_env)


# ---------- IO helpers ----------

def load_issue(date_str: str) -> Issue:
    path = AGENDAS_DIR / f"{date_str}.yaml"
    if not path.exists():
        abort(404, description=f"No issue for {date_str}")
    try:
        data = yaml.safe_load(path.read_text())
        return Issue.model_validate(data)
    except ValidationError as e:
        abort(422, description=str(e))


def save_issue_to_disk(issue: Issue) -> Path:
    AGENDAS_DIR.mkdir(parents=True, exist_ok=True)
    path = AGENDAS_DIR / f"{issue.meeting_date.isoformat()}.yaml"
    data = issue.model_dump(mode="json", exclude_none=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return path


def most_recent_date() -> str | None:
    if not AGENDAS_DIR.exists():
        return None
    dates = sorted(p.stem for p in AGENDAS_DIR.glob("*.yaml"))
    return dates[-1] if dates else None


def blank_issue(meeting_date: date) -> Issue:
    """Minimal scaffold for a new issue."""
    return Issue(
        issue_number=1,
        meeting_date=meeting_date,
        masthead=Masthead(
            subtitle="A reader's guide to the upcoming Village Board meeting.",
            meta=MetaRow(convening=meeting_date.strftime("%A, %B %-d · 7:00 PM")),
        ),
        headlines=[
            Headline(kicker="The Big Number", figure="—", caption="Headline caption."),
            Headline(kicker="On the Table", figure="—", caption="Headline caption."),
            Headline(kicker="For the Calendar", figure="—", caption="Headline caption."),
        ],
        sections=[
            StudySection(items=[]),
            RegularCompactSection(items=[]),
            ConsentSection(summary="", items=[]),
            CivicNotesSection(blocks=[]),
        ],
        footer=FooterStrip(
            meeting_details=FooterMeetingDetails(
                date_short=meeting_date.strftime("%A, %B %-d"),
                time="7:00 PM",
            ),
            editor_note_html=(
                "A curated guide to the upcoming Village Board meeting, "
                "prepared by Trustee Cory J. Wesley."
            ),
        ),
    )


# ---------- routes ----------

@app.get("/")
def index():
    latest = most_recent_date()
    if not latest:
        return redirect(url_for("new_issue"))
    return redirect(url_for("show_issue", date_str=latest))


@app.get("/<date_str>")
def show_issue(date_str: str):
    issue = load_issue(date_str)
    return render_template("snapshot.html.j2", issue=issue)


@app.get("/edit/<date_str>")
def edit_issue(date_str: str):
    issue = load_issue(date_str)
    initial_snapshot = render_template("snapshot.html.j2", issue=issue)
    return render_template(
        "editor.html",
        issue=issue,
        initial_snapshot_html=initial_snapshot,
        flash=request.args.get("flash"),
        flash_kind=request.args.get("flash_kind"),
    )


@app.post("/preview")
def preview_issue():
    """Lenient preview: render the snapshot from current form state.

    Validation errors render an inline error fragment inside the preview pane
    so the editor never silently stops updating.
    """
    raw_items = list(request.form.items(multi=True))
    data = form_to_issue_dict(raw_items)
    try:
        issue = Issue.model_validate(data)
    except ValidationError as e:
        return render_template(
            "partials/preview_pane.html",
            snapshot_html=_validation_error_html(str(e)),
        )
    snapshot = render_template("snapshot.html.j2", issue=issue)
    return render_template("partials/preview_pane.html", snapshot_html=snapshot)


def _validation_error_html(message: str) -> str:
    return (
        "<!DOCTYPE html><html><body style='font-family:Georgia,serif;padding:24px;"
        "background:#f6f1e6;color:#1a1a1a;line-height:1.5'>"
        "<h2 style='color:#ff3eb6;margin:0 0 12px'>Validation error — fix the form to "
        "see the preview again.</h2>"
        "<pre style='white-space:pre-wrap;font-size:12px;background:#fff;border:1px solid "
        "#ddd;padding:12px'>" + message.replace("<", "&lt;") + "</pre>"
        "</body></html>"
    )


@app.post("/save/<date_str>")
def save_issue(date_str: str):
    # Items from the form preserve DOM order (incl. duplicates for hidden+checkbox pairs).
    raw_items = list(request.form.items(multi=True))
    data = form_to_issue_dict(raw_items)
    try:
        issue = Issue.model_validate(data)
    except ValidationError as e:
        # Reload the existing issue (so the form stays populated) and show errors.
        try:
            existing = load_issue(date_str)
        except Exception:
            existing = blank_issue(date.fromisoformat(date_str))
        return render_template(
            "editor.html",
            issue=existing,
            flash=str(e),
            flash_kind="err",
        ), 422

    save_issue_to_disk(issue)

    # If the meeting_date changed, redirect to the new URL.
    new_date_str = issue.meeting_date.isoformat()
    if new_date_str != date_str:
        old_path = AGENDAS_DIR / f"{date_str}.yaml"
        if old_path.exists():
            old_path.unlink()
        return redirect(
            url_for("edit_issue", date_str=new_date_str)
            + "?flash=Saved+(date+changed)&flash_kind=ok"
        )

    return redirect(
        url_for("edit_issue", date_str=new_date_str) + "?flash=Saved&flash_kind=ok"
    )


@app.get("/legistar/events")
def legistar_events():
    """Return a JSON list of recent Board of Trustees events for the picker."""
    try:
        slug = _cached_client()
        body_id = find_board_body_id(slug)
        events = list_events(slug, body_id, limit=20)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(
        {"events": [event_summary(e) for e in events], "client": slug}
    )


@app.post("/legistar/import")
def legistar_import():
    """Fetch a Legistar event, bucket items, write a new YAML, redirect to edit."""
    payload = request.get_json(silent=True) or request.form
    try:
        event_id = int(payload.get("event_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "event_id required"}), 400
    # issue_number: pick max(existing) + 1 unless provided
    if payload.get("issue_number"):
        try:
            issue_number = int(payload.get("issue_number"))
        except (TypeError, ValueError):
            return jsonify({"error": "issue_number must be int"}), 400
    else:
        issue_number = _next_issue_number()

    try:
        issue = import_event(event_id, issue_number=issue_number)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    save_issue_to_disk(issue)
    return jsonify(
        {
            "ok": True,
            "date": issue.meeting_date.isoformat(),
            "edit_url": url_for(
                "edit_issue", date_str=issue.meeting_date.isoformat()
            ),
            "issue_number": issue.issue_number,
            "triage_count": len(issue.triage),
        }
    )


def _next_issue_number() -> int:
    if not AGENDAS_DIR.exists():
        return 1
    nums = []
    for p in AGENDAS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(p.read_text())
            nums.append(int(data.get("issue_number", 0)))
        except Exception:
            continue
    return (max(nums) + 1) if nums else 1


@app.post("/render/<date_str>")
def render_export(date_str: str):
    """Render an issue to HTML + PNG on disk. Returns JSON with public paths."""
    issue = load_issue(date_str)
    try:
        html_path, png_path = render_both(issue, OUT_DIR)
    except Exception as e:
        # PNG might fail (e.g. no browser); fall back to HTML-only and surface
        # the error.
        html_path = write_html(issue, OUT_DIR)
        return (
            jsonify(
                {
                    "html": url_for("serve_out", path=html_path.name),
                    "png": None,
                    "error": f"PNG rendering failed: {e!s}",
                }
            ),
            207,
        )
    return jsonify(
        {
            "html": url_for("serve_out", path=html_path.name),
            "png": url_for("serve_out", path=png_path.name),
        }
    )


@app.get("/out/<path:path>")
def serve_out(path: str):
    return send_from_directory(OUT_DIR, path)


@app.get("/new")
def new_issue():
    """Create a blank scaffold for today; redirect into the editor."""
    today = date.today()
    path = AGENDAS_DIR / f"{today.isoformat()}.yaml"
    if not path.exists():
        save_issue_to_disk(blank_issue(today))
    return redirect(url_for("edit_issue", date_str=today.isoformat()))


if __name__ == "__main__":
    app.run(debug=True)
