"""Pydantic models for an Issue of The Agenda.

The YAML shape is the source of truth for an issue's content. Auto-generated
chrome (section numbering, eyebrows, summary stats) is computed at render time
from this model — never stored in YAML.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------- shared leaf models ----------

class Pullquote(BaseModel):
    label: str
    text: str


class Headline(BaseModel):
    kicker: str
    figure: str
    caption: str


class MetaRow(BaseModel):
    convening: str
    where: str = "Council Chambers, Village Hall"
    how_to_join_html: str = (
        'In person, or virtually via the Clerk at '
        '<a href="mailto:clerkwaters@oak-park.us">clerkwaters@oak-park.us</a>'
    )


class Masthead(BaseModel):
    eyebrow_link_text: str = "Read the full agenda packet"
    eyebrow_link_url: str = (
        "https://www.oak-park.us/Government/Meetings/Village-Board-Agendas-Minutes-Videos"
    )
    subtitle: str
    meta: MetaRow


# ---------- section: feature ----------

class FeatureArticle(BaseModel):
    tag: str
    headline: str
    legistar_ids: list[str] = []
    body_md: str
    pullquote: Pullquote | None = None


class FeatureSection(BaseModel):
    kind: Literal["feature"] = "feature"
    title: str
    eyebrow: str | None = None
    articles: list[FeatureArticle]

    def is_present(self) -> bool:
        return bool(self.articles)

    def computed_eyebrow(self) -> str:
        if self.eyebrow:
            return self.eyebrow
        n = len(self.articles)
        return f"{n} feature{'s' if n != 1 else ''}"


# ---------- section: study ----------

class StudyItem(BaseModel):
    tag: str = "Study Session"
    headline: str
    body: str
    legistar_ids: list[str] = []


class StudySection(BaseModel):
    kind: Literal["study"] = "study"
    title: str = "Study Sessions"
    eyebrow: str | None = None
    items: list[StudyItem]

    def is_present(self) -> bool:
        return bool(self.items)

    def computed_eyebrow(self) -> str:
        return self.eyebrow or "Discussion items · No votes"


# ---------- section: regular_compact ----------

class RegularItem(BaseModel):
    tag: str
    name: str
    legistar_ids: list[str] = []
    text: str


class RegularCompactSection(BaseModel):
    kind: Literal["regular_compact"] = "regular_compact"
    title: str = "Also on the Regular Agenda"
    eyebrow: str | None = None
    items: list[RegularItem]

    def is_present(self) -> bool:
        return bool(self.items)

    def computed_eyebrow(self) -> str:
        if self.eyebrow:
            return self.eyebrow
        votes = sum(1 for it in self.items if "vote" in it.tag.lower())
        reports = sum(1 for it in self.items if "report" in it.tag.lower())
        n = len(self.items)
        parts: list[str] = [f"{n} item{'s' if n != 1 else ''}"]
        sub: list[str] = []
        if votes:
            sub.append(f"{votes} vote{'s' if votes != 1 else ''}")
        if reports:
            sub.append(f"{reports} report{'s' if reports != 1 else ''}")
        if sub:
            parts.append(", ".join(sub))
        return " · ".join(parts)


# ---------- section: consent ----------

class ConsentItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(max_length=80)
    legistar_id: str = ""
    flag: bool = False
    why: str = ""
    cost: float | None = None


class ConsentSection(BaseModel):
    kind: Literal["consent"] = "consent"
    title: str = "Consent Agenda"
    summary: str
    items: list[ConsentItem]
    minimal: bool = False
    """If True, only flagged items render in the list (full count still in eyebrow)."""

    def is_present(self) -> bool:
        return bool(self.items)

    def computed_eyebrow(self) -> str:
        n = len(self.items)
        return f"{n} item{'s' if n != 1 else ''} · No discussion"

    def visible_items(self) -> list[ConsentItem]:
        if self.minimal:
            return [it for it in self.items if it.flag]
        return list(self.items)


# ---------- section: civic_notes ----------

class Proclamation(BaseModel):
    name: str
    when: str


class CivicProclamations(BaseModel):
    kind: Literal["proclamations"] = "proclamations"
    label: str
    items: list[Proclamation]


class CivicBody(BaseModel):
    kind: Literal["body"] = "body"
    label: str
    body_html: str
    legistar_id: str = ""
    side: bool = True
    """True → blue-deep label tone (`.civic-block.side`)."""


CivicBlock = Annotated[
    CivicProclamations | CivicBody, Field(discriminator="kind")
]


class CivicNotesSection(BaseModel):
    kind: Literal["civic_notes"] = "civic_notes"
    title: str = "Civic Notes"
    eyebrow: str | None = None
    blocks: list[CivicBlock]

    def is_present(self) -> bool:
        return bool(self.blocks)

    def computed_eyebrow(self) -> str:
        if self.eyebrow:
            return self.eyebrow
        labels: list[str] = []
        seen_proc = False
        for b in self.blocks:
            if b.kind == "proclamations":
                labels.append("Proclamations" if len(b.items) != 1 else "Proclamation")
                seen_proc = True
            else:
                # categorize body blocks by label keyword
                key = b.label.lower()
                if "appoint" in key:
                    labels.append("Appointments")
                elif "vacanc" in key:
                    labels.append("Vacancies")
                else:
                    labels.append(b.label)
        if not seen_proc:
            return " · ".join(labels)
        return " · ".join(labels)


# ---------- discriminated union over all sections ----------

Section = Annotated[
    FeatureSection
    | StudySection
    | RegularCompactSection
    | ConsentSection
    | CivicNotesSection,
    Field(discriminator="kind"),
]


# ---------- footer ----------

class FooterMeetingDetails(BaseModel):
    date_short: str
    time: str
    location: str = "Village Hall · Council Chambers"


class FooterStrip(BaseModel):
    headline_html: str = 'Make your voice <span class="accent">heard.</span>'
    public_comment_html: str = (
        "Public comments may be made at the start of the meeting and as agenda items "
        "are discussed. To comment virtually, contact the Clerk by "
        "<strong>5:00 PM on the day of the meeting</strong> at "
        "<strong>708-358-5670</strong> or "
        '<a href="mailto:publiccomment@oak-park.us">publiccomment@oak-park.us</a>. '
        "Camera on, three minutes per speaker."
    )
    meeting_details: FooterMeetingDetails
    editor_note_html: str


# ---------- the issue ----------

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


class TriageItem(BaseModel):
    """Legistar items not yet placed into a section — wait in the triage drawer."""
    name: str
    legistar_id: str = ""
    agenda_section: str = ""
    matter_type: str = ""
    raw_title: str = ""


class Issue(BaseModel):
    issue_number: int = Field(ge=1, le=999)
    meeting_date: date
    page_title: str | None = None
    """If absent, derived as 'The Agenda · {meeting_date}'."""
    masthead: Masthead
    headlines: list[Headline] = Field(min_length=3, max_length=3)
    sections: list[Section]
    footer: FooterStrip
    triage: list[TriageItem] = []
    legistar_event_id: int | None = None

    def present_sections(self) -> list[tuple[str, Section]]:
        """Yield (roman_numeral, section) for sections that should render."""
        out: list[tuple[str, Section]] = []
        for sec in self.sections:
            if sec.is_present():
                idx = len(out)
                if idx >= len(ROMAN):
                    raise ValueError("Too many present sections for fixed roman list")
                out.append((ROMAN[idx], sec))
        return out

    def issue_label(self) -> str:
        return f"Issue {self.issue_number:02d} · " + self.meeting_date.strftime(
            "%B %-d, %Y"
        )

    def computed_page_title(self) -> str:
        return self.page_title or "The Agenda · " + self.meeting_date.strftime(
            "%B %-d, %Y"
        )

    @model_validator(mode="after")
    def _no_consent_and_regular_in_same_section(self) -> Issue:
        # Cross-cutting rule: consent and regular_compact are separate sections.
        # The schema already enforces this via discriminated union — this hook
        # is a placeholder for future cross-section invariants.
        return self
