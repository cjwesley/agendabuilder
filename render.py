"""Render an Issue to HTML and PNG.

HTML rendering is via Jinja2 (Flask render_template). PNG rendering uses
Playwright/Chromium against the rendered HTML file.

Browser discovery (in priority order):
    1. PLAYWRIGHT_CHROMIUM_EXECUTABLE env var — explicit path
    2. PLAYWRIGHT_BROWSERS_PATH env var — Playwright's standard browsers dir;
       glob for the chromium binary inside (covers the sandbox's
       /opt/pw-browsers preinstall)
    3. Default Playwright lookup (works in the production Docker image,
       which is based on mcr.microsoft.com/playwright/python)
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from flask import render_template
from markdown_it import MarkdownIt

from schema import Issue

_md = MarkdownIt("commonmark", {"breaks": False, "html": True})


# ---------- Jinja filters ----------

def markdown_with_dropcap(text: str) -> str:
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
    env.filters["markdown_with_dropcap"] = markdown_with_dropcap
    env.filters["join_ids"] = join_ids
    env.filters["format_meeting_date"] = format_meeting_date


# ---------- HTML output ----------

def render_html(issue: Issue) -> str:
    """Render the snapshot template. Flask request context required."""
    return render_template("snapshot.html.j2", issue=issue)


def write_html(issue: Issue, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(issue)
    out_path = out_dir / f"{issue.meeting_date.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ---------- PNG output ----------

def _discover_chromium() -> str | None:
    explicit = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return explicit
    browsers_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if browsers_root:
        candidates = sorted(
            glob.glob(f"{browsers_root}/chromium-*/chrome-linux/chrome"),
            reverse=True,
        )
        if candidates:
            return candidates[0]
    # Final fallback: nothing — let Playwright try its default lookup, which
    # works in the production Playwright Docker image.
    return None


def write_png(issue: Issue, out_dir: Path) -> Path:
    """Render the snapshot HTML and screenshot it to PNG."""
    from playwright.sync_api import sync_playwright  # imported lazily

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = write_html(issue, out_dir)
    png_path = out_dir / f"{issue.meeting_date.isoformat()}.png"
    file_url = "file://" + str(html_path.resolve())

    launch_kwargs: dict = {"headless": True}
    exe = _discover_chromium()
    if exe:
        launch_kwargs["executable_path"] = exe

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(
                viewport={"width": 1080, "height": 1600},
                device_scale_factor=2,
            )
            page.goto(file_url, wait_until="networkidle")
            page.screenshot(path=str(png_path), full_page=True)
        finally:
            browser.close()
    return png_path


def render_both(issue: Issue, out_dir: Path) -> tuple[Path, Path]:
    """Render HTML and PNG. Returns (html_path, png_path)."""
    html_path = write_html(issue, out_dir)
    png_path = write_png(issue, out_dir)
    return html_path, png_path
