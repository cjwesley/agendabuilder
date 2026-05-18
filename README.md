# The Agenda Engine

Solo-author publication tool that turns the Oak Park Village Board agenda
packet into a curated snapshot. Form editor → live preview → HTML + PNG
output → YAML-archived issues, with first-draft copy from Claude and a
one-click pull from Legistar.

Trustee Cory J. Wesley uses this to publish *The Agenda* — see the two
reference renders in this repo: `oak_park_agenda_wesley_may12_pressuretest.html`
and `oak_park_agenda_wesley_feb10_v7_masthead.html`.

## Local development

```sh
uv sync
uv run playwright install chromium       # one-time, for PNG rendering
uv run flask --app app run
```

Open <http://localhost:5000>. The most recent agenda in `agendas/` loads;
open `/edit/<YYYY-MM-DD>` to edit.

For PNG rendering against a pre-installed Chromium (CI / sandbox), set
`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` or
`PLAYWRIGHT_CHROMIUM_EXECUTABLE=/abs/path/to/chrome`.

To enable AI drafting and Legistar pull, set the matching env vars:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
export LEGISTAR_CLIENT=oakpark    # optional; auto-discovered if absent
```

## Run the tests

```sh
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers uv run pytest tests/
```

52 cases cover schema validation, render fidelity, the editor save
round-trip, HTMX preview, the Playwright render pipeline (with a graceful
skip when no browser is discoverable), Legistar bucketing, the AI
drafter (Anthropic SDK fully mocked), and basic-auth gating.

## Deploy to Fly.io

```sh
fly launch --no-deploy --copy-config        # picks up fly.toml; do not overwrite
fly volumes create agenda_data    --region ord --size 1
fly volumes create agenda_renders --region ord --size 5
fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  LEGISTAR_CLIENT=oakpark \
  BASIC_AUTH_USER=cory \
  BASIC_AUTH_PASS="$(head -c 32 /dev/urandom | base64)"
fly deploy
```

`agendas/` mounts the YAML archive, `out/` mounts the rendered HTML+PNG —
both survive machine restarts. The machine auto-stops after idle and
auto-starts on request; expect ~5s cold-start latency on the first hit.

Health check at `/healthz` is unauthenticated; everything else requires
the basic-auth pair when `BASIC_AUTH_USER` and `BASIC_AUTH_PASS` are set.

## Layout

```
app.py                  Flask routes (edit, save, preview, render, legistar, draft)
schema.py               Pydantic v2 Issue + Section discriminated union + Triage
formparse.py            HTML-form bracket-paths → nested dict for Pydantic
render.py               Jinja2 filters (markdown_with_dropcap) + Playwright PNG
legistar.py             Legistar REST client + bucketing into Issue scaffolds
drafter.py              Claude Opus 4.7 — feature / study / compact drafts

templates/
  snapshot.html.j2      The parameterized agenda snapshot
  editor.html           Two-pane editor shell
  partials/
    form_section.html   Per-kind form rendering
    preview_pane.html   HTMX swap target for live preview

static/
  editor.css            Editor chrome
  editor.js             Render-mode toggle, char counters, export, Legistar, AI draft
  assets/logo.png       Logo banner

prompts/
  voice_guide.md        Voice rules — cached in every drafter system prompt
  feature_draft.md      Feature-specific length budgets + guidance
  study_draft.md        Study-specific length budgets + guidance
  compact_draft.md      Compact-note length budget + guidance

agendas/                YAML archive (one file per issue) — Fly volume in prod
out/                    Rendered HTML + PNG — Fly volume in prod

Dockerfile              Playwright base image + uv-managed deps
fly.toml                ord region, 1GB shared CPU, two persistent volumes
```

## Source-of-truth hierarchy

- **`may12_pressuretest.html` is the authoritative styling source.** All
  CSS comes from it verbatim. The Pydantic schema and rendered HTML target
  this file for visual parity.
- **`feb10_v7_masthead.html` is referenced only for content that does not
  exist in may12 — currently the Feature section.** Feb10 supplies the
  structural shape of a Feature (class names, nesting); Feature CSS is
  written fresh to match may12's compact rhythm. Feb10's footer, body
  type sizes, section spacing, and label treatments are prior iterations
  we already moved past.

This rule is enforced in code and documented in `AGENDA_ENGINE_BRIEF.md`.
