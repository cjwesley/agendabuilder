"""Pass 2: render-fidelity spot checks.

For each fixture we assert:
  - Pydantic load succeeds
  - The rendered HTML contains landmark strings unique to that issue
  - Section numbering is correct (auto-renumbered, not hard-coded)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app import app
from schema import Issue

FIXTURES = ["2026-02-10", "2026-05-12"]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("date_str", FIXTURES)
def test_yaml_validates(date_str):
    path = Path(__file__).parent.parent / "agendas" / f"{date_str}.yaml"
    data = yaml.safe_load(path.read_text())
    issue = Issue.model_validate(data)
    assert issue.meeting_date.isoformat() == date_str
    assert len(issue.headlines) == 3


def test_feb10_render(client):
    resp = client.get("/2026-02-10")
    assert resp.status_code == 200
    html = resp.data.decode()

    # masthead + headlines
    assert "Issue 02 · February 10, 2026" in html
    assert "$1.685M" in html
    assert "1106" in html

    # § I = Features
    assert "§ I" in html
    assert "Madison Street &amp; the Municipal Campus" in html or \
           "Madison Street & the Municipal Campus" in html
    assert 'class="feature"' in html
    assert 'class="drop-cap"' in html
    assert 'class="pullquote"' in html

    # § II = Regular, § III = Consent (minimal), § IV = Civic
    assert "§ II" in html
    assert "§ III" in html
    assert "§ IV" in html
    assert 'class="consent-list consent-list-minimal"' in html
    assert "13 items · No discussion" in html
    # Only 4 flagged rows render in minimal mode
    assert html.count('class="consent-row flagged"') == 4
    assert 'class="consent-row"' not in html.replace('class="consent-row flagged"', "")


def test_may12_render(client):
    resp = client.get("/2026-05-12")
    assert resp.status_code == 200
    html = resp.data.decode()

    assert "Issue 03 · May 12, 2026" in html
    assert "Three Study Sessions" in html

    # § I = Study (no Features this issue → renumbered)
    assert "§ I" in html
    assert 'class="study"' in html
    assert "Features" not in html or "Feature" not in html  # no feature section heading
    # Note: 'feature-' classes won't appear because there's no feature section.
    assert 'class="feature"' not in html

    # § II = Regular
    assert "§ II" in html
    assert "CPOC semi-annual report" in html

    # § III = Consent (full mode, 7 items)
    assert "§ III" in html
    assert "7 items · No discussion" in html
    # full list mode → no minimal class applied (CSS still defines it inline)
    assert 'class="consent-list consent-list-minimal"' not in html
    assert 'class="consent-list"' in html
    # 3 flagged + 4 unflagged = 7 rows
    assert html.count('class="consent-row flagged"') == 3
    plain = html.count('<div class="consent-row">')
    assert plain == 4, f"expected 4 plain consent rows, got {plain}"

    # § IV = Civic Notes
    assert "§ IV" in html
    assert "civic-block side" in html
    assert "Four Proclomations" not in html  # sanity: no typo
    assert "Four Proclamations for May" in html


def test_section_renumbering(client):
    """Removing all items from a leading section should bump the rest up."""
    feb = client.get("/2026-02-10").data.decode()
    may = client.get("/2026-05-12").data.decode()
    # Feb has Features at § I; May has Study at § I (Features absent).
    assert ">§ I</span>" in feb
    assert ">§ I</span>" in may
    # Feb's study would be § II if present — it isn't, so Regular gets § II.
    feb_regular_pos = feb.index("Also on the Regular Agenda")
    feb_section_ii = feb.index(">§ II</span>")
    assert feb_section_ii < feb_regular_pos


def test_dropcap_first_paragraph_only(client):
    html = client.get("/2026-02-10").data.decode()
    # First feature has 2 paragraphs → exactly 1 drop-cap inside its feature-body
    assert html.count('<p class="drop-cap">') == 2  # one per feature article
