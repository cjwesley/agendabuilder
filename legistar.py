"""Legistar API client + bucketing into Issue scaffolds.

API docs: https://webapi.legistar.com/

Client slug is the URL prefix that identifies the Village's tenant
(`https://webapi.legistar.com/v1/{client}/...`). Oak Park's slug isn't
documented publicly, so discover_client() probes likely candidates.

All HTTP via httpx — easy to mock with respx in tests.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import httpx

from schema import (
    CivicBody,
    CivicNotesSection,
    CivicProclamations,
    ConsentItem,
    ConsentSection,
    FooterMeetingDetails,
    FooterStrip,
    Headline,
    Issue,
    Masthead,
    MetaRow,
    Proclamation,
    RegularCompactSection,
    RegularItem,
    StudySection,
    TriageItem,
)

log = logging.getLogger(__name__)

BASE = "https://webapi.legistar.com/v1"
CANDIDATE_CLIENTS = ["oakpark", "villageofoakpark", "oak-park"]
BOARD_BODY_NAME = "President and Board of Trustees"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


# ---------- client discovery & lookups ----------

def discover_client(http: httpx.Client | None = None) -> str:
    """Probe Legistar for the Village's tenant slug. Returns first 200 hit."""
    override = os.environ.get("LEGISTAR_CLIENT")
    if override:
        return override
    client = http or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        for slug in CANDIDATE_CLIENTS:
            url = f"{BASE}/{slug}/Bodies"
            resp = client.get(url, params={"$top": 1})
            if resp.status_code == 200:
                log.info("Legistar client discovered: %s", slug)
                return slug
        raise RuntimeError(
            "Could not discover Legistar client slug; "
            "set LEGISTAR_CLIENT env var explicitly."
        )
    finally:
        if http is None:
            client.close()


@lru_cache(maxsize=8)
def _cached_client() -> str:
    return discover_client()


def find_board_body_id(slug: str, http: httpx.Client | None = None) -> int:
    """Look up the BodyId for the President and Board of Trustees."""
    client = http or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        # Filter on BodyName eq '...' if Legistar supports it; otherwise scan.
        resp = client.get(
            f"{BASE}/{slug}/Bodies",
            params={"$filter": f"BodyName eq '{BOARD_BODY_NAME}'"},
        )
        resp.raise_for_status()
        bodies = resp.json()
        if bodies:
            return int(bodies[0]["BodyId"])
        # Fallback: scan all and match case-insensitively.
        resp = client.get(f"{BASE}/{slug}/Bodies")
        resp.raise_for_status()
        for b in resp.json():
            if b.get("BodyName", "").strip().lower() == BOARD_BODY_NAME.lower():
                return int(b["BodyId"])
        raise RuntimeError(f"Couldn't find body '{BOARD_BODY_NAME}' under {slug}")
    finally:
        if http is None:
            client.close()


def list_events(
    slug: str,
    body_id: int,
    *,
    limit: int = 10,
    http: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return upcoming + recent events for the body, newest first."""
    client = http or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(
            f"{BASE}/{slug}/Events",
            params={
                "$filter": f"EventBodyId eq {body_id}",
                "$orderby": "EventDate desc",
                "$top": limit,
            },
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if http is None:
            client.close()


def fetch_event_items(
    slug: str,
    event_id: int,
    *,
    http: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Pull all agenda items for an event, with matter attachments expanded."""
    client = http or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(
            f"{BASE}/{slug}/Events/{event_id}/EventItems",
            params={
                "$expand": "EventItemMatterAttachments",
                "$orderby": "EventItemMinutesSequence",
            },
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if http is None:
            client.close()


# ---------- bucketing ----------

def _legistar_id(item: dict[str, Any]) -> str:
    """Build a 'PFX YY-NNN' style id from the matter file number, if any."""
    raw = item.get("EventItemMatterFile") or ""
    return raw.strip()


def _matter_type_prefix(item: dict[str, Any]) -> str:
    """Best-effort: 'RES', 'ORD', 'MOT', 'ID' depending on matter type."""
    mt = (item.get("EventItemMatterType") or "").strip().lower()
    if "resolution" in mt:
        return "RES"
    if "ordinance" in mt:
        return "ORD"
    if "motion" in mt or "minute" in mt:
        return "MOT"
    return "ID"


def _classify(section: str) -> str:
    """Return one of: 'consent', 'regular', 'proclamation', 'appointment',
    'vacancy', 'triage'."""
    s = (section or "").lower()
    if "consent" in s:
        return "consent"
    if "regular agenda" in s or s == "regular":
        return "regular"
    if "proclamation" in s:
        return "proclamation"
    if "appoint" in s:
        return "appointment"
    if "vacanc" in s or "open seat" in s:
        return "vacancy"
    return "triage"


def bucket_to_issue(
    items: list[dict[str, Any]],
    *,
    issue_number: int,
    meeting_date: date,
    subtitle: str = "A reader's guide to the upcoming Village Board meeting.",
) -> Issue:
    """Convert raw Legistar EventItems into an Issue draft."""
    consent_items: list[ConsentItem] = []
    regular_items: list[RegularItem] = []
    procs: list[Proclamation] = []
    appointments: list[CivicBody] = []
    vacancies: list[CivicBody] = []
    triage: list[TriageItem] = []

    for it in items:
        title = (it.get("EventItemTitle") or "").strip()
        section = (it.get("EventItemAgendaSection") or "").strip()
        legistar_id = _legistar_id(it)
        kind = _classify(section)

        if kind == "consent":
            consent_items.append(
                ConsentItem(
                    name=title[:80] or f"Item {it.get('EventItemMinutesSequence', '?')}",
                    legistar_id=legistar_id,
                )
            )
        elif kind == "regular":
            regular_items.append(
                RegularItem(
                    tag="Regular Agenda · Up for vote",
                    name=title,
                    text="",
                    legistar_ids=[legistar_id] if legistar_id else [],
                )
            )
        elif kind == "proclamation":
            month = meeting_date.strftime("%B %Y")
            when = f"{month} · {legistar_id}" if legistar_id else month
            procs.append(Proclamation(name=title, when=when))
        elif kind == "appointment":
            appointments.append(
                CivicBody(
                    kind="body",
                    label="Appointments",
                    body_html=title,
                    legistar_id=legistar_id,
                    side=True,
                )
            )
        elif kind == "vacancy":
            vacancies.append(
                CivicBody(
                    kind="body",
                    label="Open Vacancies",
                    body_html=title,
                    legistar_id=legistar_id,
                    side=True,
                )
            )
        else:
            triage.append(
                TriageItem(
                    name=title,
                    legistar_id=legistar_id,
                    agenda_section=section,
                    matter_type=(it.get("EventItemMatterType") or "").strip(),
                    raw_title=title,
                )
            )

    # Assemble sections in canonical order; empty ones drop out via
    # Issue.present_sections() at render time.
    sections: list = []

    sections.append(
        StudySection(
            title="Study Sessions",
            eyebrow="Discussion items · No votes",
            items=[],
        )
    )
    sections.append(
        RegularCompactSection(
            title="Also on the Regular Agenda",
            items=regular_items,
        )
    )
    sections.append(
        ConsentSection(
            summary=(
                f"<strong>{sum(1 for c in consent_items if c.flag)} item(s)</strong> "
                f"flagged for a second look. <strong>{len(consent_items)} total</strong>."
            )
            if consent_items
            else "",
            items=consent_items,
            minimal=len(consent_items) > 8,
        )
    )
    civic_blocks: list = []
    if procs:
        month_name = meeting_date.strftime("%B")
        civic_blocks.append(
            CivicProclamations(label=f"Proclamations for {month_name}", items=procs)
        )
    civic_blocks.extend(vacancies)
    civic_blocks.extend(appointments)
    sections.append(CivicNotesSection(blocks=civic_blocks))

    return Issue(
        issue_number=issue_number,
        meeting_date=meeting_date,
        masthead=Masthead(
            subtitle=subtitle,
            meta=MetaRow(convening=meeting_date.strftime("%A, %B %-d · 7:00 PM")),
        ),
        headlines=[
            Headline(kicker="The Big Number", figure="—", caption=""),
            Headline(kicker="On the Table", figure="—", caption=""),
            Headline(kicker="For the Calendar", figure="—", caption=""),
        ],
        sections=sections,
        footer=FooterStrip(
            meeting_details=FooterMeetingDetails(
                date_short=meeting_date.strftime("%A, %B %-d"),
                time="7:00 PM",
            ),
            editor_note_html=(
                f"A curated guide to the {meeting_date.strftime('%B %-d, %Y')} "
                "Village Board meeting, prepared by Trustee Cory J. Wesley."
            ),
        ),
        triage=triage,
    )


# ---------- high-level orchestrators (used by Flask routes) ----------

def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    """Strip a Legistar event down to the fields the picker UI needs."""
    raw_date = event.get("EventDate")
    parsed: date | None = None
    if raw_date:
        try:
            parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return {
        "event_id": event.get("EventId"),
        "date": parsed.isoformat() if parsed else None,
        "time": event.get("EventTime"),
        "location": event.get("EventLocation"),
        "agenda_status": event.get("EventAgendaStatusName"),
    }


def import_event(
    event_id: int,
    *,
    issue_number: int,
    slug: str | None = None,
    http: httpx.Client | None = None,
) -> Issue:
    """Fetch + bucket a Legistar event into a fresh Issue draft."""
    slug = slug or _cached_client()
    items = fetch_event_items(slug, event_id, http=http)
    if not items:
        raise RuntimeError(f"Legistar event {event_id} has no items")
    # Use the EventDate of the first item-affiliated event if present;
    # otherwise the caller should provide explicitly.
    meeting_date_raw = items[0].get("EventDate") or items[0].get("MatterAgendaDate")
    try:
        meeting_date = (
            datetime.fromisoformat(meeting_date_raw.replace("Z", "+00:00")).date()
            if meeting_date_raw
            else date.today()
        )
    except (AttributeError, ValueError):
        meeting_date = date.today()
    issue = bucket_to_issue(
        items, issue_number=issue_number, meeting_date=meeting_date
    )
    issue.legistar_event_id = event_id
    return issue
