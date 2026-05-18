"""Pass 6: Legistar client + bucketing into Issue scaffolds."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from legistar import (
    BASE,
    _classify,
    bucket_to_issue,
    discover_client,
    fetch_event_items,
    find_board_body_id,
    list_events,
)


@pytest.fixture
def http():
    with httpx.Client() as c:
        yield c


# ---------- pure-logic ----------

@pytest.mark.parametrize(
    "section, expected",
    [
        ("Consent Agenda", "consent"),
        ("CONSENT AGENDA", "consent"),
        ("Regular Agenda", "regular"),
        ("Regular", "regular"),
        ("Proclamation", "proclamation"),
        ("Appointments", "appointment"),
        ("Vacancies", "vacancy"),
        ("Public Hearing", "triage"),
        ("First Reading", "triage"),
        ("", "triage"),
    ],
)
def test_classify(section, expected):
    assert _classify(section) == expected


def test_bucket_to_issue_distributes_items():
    items = [
        # 2 consent
        {
            "EventItemTitle": "Bayan Ceramics — Class D-19 liquor",
            "EventItemAgendaSection": "Consent Agenda",
            "EventItemMatterFile": "ORD 26-137",
            "EventItemMatterType": "Ordinance",
        },
        {
            "EventItemTitle": "Closed session minutes approval — 18 dates",
            "EventItemAgendaSection": "Consent Agenda",
            "EventItemMatterFile": "MOT 26-163",
        },
        # 1 regular
        {
            "EventItemTitle": "Cohousing escrow waiver",
            "EventItemAgendaSection": "Regular Agenda",
            "EventItemMatterFile": "RES 26-198",
        },
        # 1 proclamation
        {
            "EventItemTitle": "National Public Works Week",
            "EventItemAgendaSection": "Proclamation",
            "EventItemMatterFile": "MOT 26-161",
        },
        # 1 appointment
        {
            "EventItemTitle": "Jane Doe to the Citizen Involvement Commission",
            "EventItemAgendaSection": "Appointments",
            "EventItemMatterFile": "MOT 26-116",
        },
        # 1 triage (Public Hearing → triage)
        {
            "EventItemTitle": "Public hearing on 6549 North Avenue",
            "EventItemAgendaSection": "Public Hearing",
            "EventItemMatterFile": "ORD 26-104",
            "EventItemMatterType": "Ordinance",
        },
    ]
    issue = bucket_to_issue(items, issue_number=4, meeting_date=date(2026, 5, 26))

    # find sections by kind
    by_kind = {s.kind: s for s in issue.sections}
    consent = by_kind["consent"]
    regular = by_kind["regular_compact"]
    civic = by_kind["civic_notes"]

    assert len(consent.items) == 2
    assert len(regular.items) == 1
    # civic has procs + appointments (no vacancies in this fixture)
    civic_kinds = [b.kind for b in civic.blocks]
    assert "proclamations" in civic_kinds
    # 1 appointment body block
    appt_blocks = [b for b in civic.blocks if b.kind == "body" and "Appointments" in b.label]
    assert len(appt_blocks) == 1

    # triage caught the public-hearing item
    assert len(issue.triage) == 1
    assert issue.triage[0].agenda_section == "Public Hearing"


def test_bucket_to_issue_consent_summary_uses_counts():
    items = [
        {"EventItemTitle": f"item {i}", "EventItemAgendaSection": "Consent Agenda"}
        for i in range(10)
    ]
    issue = bucket_to_issue(items, issue_number=1, meeting_date=date(2026, 6, 9))
    consent = next(s for s in issue.sections if s.kind == "consent")
    assert consent.minimal is True  # 10 > 8 threshold
    assert "10 total" in consent.summary


# ---------- HTTP-mocked ----------

@respx.mock
def test_discover_client_returns_first_200(http, monkeypatch):
    monkeypatch.delenv("LEGISTAR_CLIENT", raising=False)
    respx.get(f"{BASE}/oakpark/Bodies").mock(
        return_value=httpx.Response(404, json={"error": "no"})
    )
    respx.get(f"{BASE}/villageofoakpark/Bodies").mock(
        return_value=httpx.Response(200, json=[{"BodyId": 1}])
    )
    assert discover_client(http) == "villageofoakpark"


@respx.mock
def test_discover_client_env_override(http, monkeypatch):
    monkeypatch.setenv("LEGISTAR_CLIENT", "explicit-slug")
    # Should short-circuit without an HTTP call.
    assert discover_client(http) == "explicit-slug"


@respx.mock
def test_find_board_body_id(http):
    respx.get(f"{BASE}/oakpark/Bodies").mock(
        return_value=httpx.Response(
            200, json=[{"BodyId": 17, "BodyName": "President and Board of Trustees"}]
        )
    )
    assert find_board_body_id("oakpark", http=http) == 17


@respx.mock
def test_list_events(http):
    respx.get(f"{BASE}/oakpark/Events").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"EventId": 9001, "EventDate": "2026-05-12T00:00:00", "EventTime": "7:00 PM"},
                {"EventId": 9000, "EventDate": "2026-04-28T00:00:00", "EventTime": "7:00 PM"},
            ],
        )
    )
    events = list_events("oakpark", body_id=17, http=http)
    assert len(events) == 2
    assert events[0]["EventId"] == 9001


@respx.mock
def test_fetch_event_items(http):
    respx.get(f"{BASE}/oakpark/Events/9001/EventItems").mock(
        return_value=httpx.Response(200, json=[{"EventItemTitle": "A"}, {"EventItemTitle": "B"}])
    )
    items = fetch_event_items("oakpark", 9001, http=http)
    assert [it["EventItemTitle"] for it in items] == ["A", "B"]
