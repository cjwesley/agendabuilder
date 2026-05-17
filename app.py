from __future__ import annotations

from pathlib import Path

import yaml
from flask import Flask, abort, redirect, render_template, url_for
from pydantic import ValidationError

from render import install_filters
from schema import Issue

AGENDAS_DIR = Path(__file__).parent / "agendas"

app = Flask(__name__)
install_filters(app.jinja_env)


def load_issue(date_str: str) -> Issue:
    path = AGENDAS_DIR / f"{date_str}.yaml"
    if not path.exists():
        abort(404, description=f"No issue for {date_str}")
    try:
        data = yaml.safe_load(path.read_text())
        return Issue.model_validate(data)
    except ValidationError as e:
        abort(422, description=str(e))


def most_recent_date() -> str | None:
    if not AGENDAS_DIR.exists():
        return None
    dates = sorted(p.stem for p in AGENDAS_DIR.glob("*.yaml"))
    return dates[-1] if dates else None


@app.get("/")
def index():
    latest = most_recent_date()
    if not latest:
        return "No issues yet. Place a YAML at agendas/<YYYY-MM-DD>.yaml.", 404
    return redirect(url_for("show_issue", date_str=latest))


@app.get("/<date_str>")
def show_issue(date_str: str):
    issue = load_issue(date_str)
    return render_template("snapshot.html.j2", issue=issue)


if __name__ == "__main__":
    app.run(debug=True)
