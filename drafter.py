"""AI drafting for Feature articles, Study items, and Regular-compact notes.

Uses the Anthropic SDK with `claude-opus-4-7`, adaptive thinking, and
structured outputs (`messages.parse()` with a Pydantic schema).

Prompt caching: the voice guide is the same on every call, so it sits in the
system prompt with `cache_control` so we pay cache-read price after the first
draft of each session window.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
MAX_TOKENS = 16000  # generous headroom for adaptive thinking + structured output


# ---------- output schemas (what the model must return) ----------

class FeatureDraft(BaseModel):
    headline: str
    tag: str
    body_md: str
    pullquote_label: str = Field(
        default="",
        description='Empty if no quotable text is available.',
    )
    pullquote_text: str = Field(default="")


class StudyDraft(BaseModel):
    headline: str
    body: str


class CompactDraft(BaseModel):
    text: str = Field(description="One sentence, 60–180 chars.")


# ---------- prompt assembly (cached on disk) ----------

@lru_cache(maxsize=8)
def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _system_blocks(kind: str) -> list[dict]:
    """Build the system prompt as cacheable text blocks.

    Voice guide + task instructions are stable across calls in a given
    session → mark the last block with cache_control so the API treats the
    whole system prompt as cache-readable on subsequent calls.
    """
    voice = _read_prompt("voice_guide.md")
    task_file = {
        "feature": "feature_draft.md",
        "study": "study_draft.md",
        "compact": "compact_draft.md",
    }[kind]
    task = _read_prompt(task_file)
    return [
        {"type": "text", "text": voice},
        {
            "type": "text",
            "text": task,
            "cache_control": {"type": "ephemeral"},
        },
    ]


# ---------- client (lazy; raises a clear error when key is missing) ----------

@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your environment "
            "(or `fly secrets set`) to enable AI drafting."
        )
    return anthropic.Anthropic()


# ---------- seed → user-prompt rendering ----------

def _render_seed(seed: dict) -> str:
    """Human-readable summary of the Legistar item the model is drafting from."""
    lines = []
    if seed.get("title"):
        lines.append(f"Source title (verbatim from Legistar): {seed['title']}")
    if seed.get("legistar_ids"):
        lines.append("Legistar IDs: " + ", ".join(seed["legistar_ids"]))
    if seed.get("matter_type"):
        lines.append(f"Matter type: {seed['matter_type']}")
    if seed.get("agenda_section"):
        lines.append(f"Agenda section: {seed['agenda_section']}")
    if seed.get("staff_report_excerpt"):
        lines.append(
            "Staff-report excerpt (verbatim — quotable for the pullquote):\n"
            + seed["staff_report_excerpt"]
        )
    if seed.get("overview"):
        lines.append("Agenda-packet overview:\n" + seed["overview"])
    if not lines:
        lines.append("(no source material — produce a best-effort placeholder)")
    return "\n\n".join(lines)


# ---------- draft entry points ----------

def draft_feature(seed: dict) -> FeatureDraft:
    user_msg = (
        "Draft a Feature article for the following agenda item. "
        "Follow the voice guide and length budgets exactly.\n\n"
        + _render_seed(seed)
    )
    resp = _client().messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_system_blocks("feature"),
        messages=[{"role": "user", "content": user_msg}],
        output_format=FeatureDraft,
    )
    _log_usage("feature", resp)
    return resp.parsed_output


def draft_study(seed: dict) -> StudyDraft:
    user_msg = (
        "Draft a Study Session entry for the following agenda item. "
        "Follow the voice guide and length budgets exactly.\n\n"
        + _render_seed(seed)
    )
    resp = _client().messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_system_blocks("study"),
        messages=[{"role": "user", "content": user_msg}],
        output_format=StudyDraft,
    )
    _log_usage("study", resp)
    return resp.parsed_output


def draft_compact(seed: dict) -> CompactDraft:
    user_msg = (
        "Write the one-sentence editorial frame for the following agenda item. "
        "Follow the voice guide and length budget exactly.\n\n"
        + _render_seed(seed)
    )
    resp = _client().messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=_system_blocks("compact"),
        messages=[{"role": "user", "content": user_msg}],
        output_format=CompactDraft,
    )
    _log_usage("compact", resp)
    return resp.parsed_output


def _log_usage(kind: str, resp) -> None:
    u = getattr(resp, "usage", None)
    if u is None:
        return
    log.info(
        "drafter.%s usage: input=%s cache_read=%s cache_write=%s output=%s",
        kind,
        u.input_tokens,
        getattr(u, "cache_read_input_tokens", 0),
        getattr(u, "cache_creation_input_tokens", 0),
        u.output_tokens,
    )
