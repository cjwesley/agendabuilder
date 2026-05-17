"""Render an Issue to HTML via Jinja2.

PNG rendering (via Playwright) is added in Pass 5.
"""

from __future__ import annotations

from pathlib import Path

from flask import render_template
from markdown_it import MarkdownIt

from schema import Issue

_md = MarkdownIt("commonmark", {"breaks": False, "html": True})


def markdown_with_dropcap(text: str) -> str:
    """Render markdown to HTML, tagging the first <p> with class='drop-cap'.

    Used for Feature article bodies, where the first paragraph carries the
    drop cap and subsequent paragraphs render plain.
    """
    if not text:
        return ""
    html = _md.render(text).strip()
    if html.startswith("<p>"):
        html = '<p class="drop-cap">' + html[len("<p>") :]
    return html


def join_ids(ids: list[str]) -> str:
    return " · ".join(ids)


def format_meeting_date(d) -> str:
    return d.strftime("%B %-d, %Y")


def install_filters(env) -> None:
    """Attach our custom filters to a Jinja environment."""
    env.filters["markdown_with_dropcap"] = markdown_with_dropcap
    env.filters["join_ids"] = join_ids
    env.filters["format_meeting_date"] = format_meeting_date


def render_html(issue: Issue) -> str:
    """Render the snapshot template for an issue. (Flask request context required.)"""
    return render_template("snapshot.html.j2", issue=issue)


def write_html(issue: Issue, out_dir: Path) -> Path:
    """Persist the rendered HTML to out/<date>.html. (Flask request context required.)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(issue)
    out_path = out_dir / f"{issue.meeting_date.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
