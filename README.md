# The Agenda Engine

Publication engine for Trustee Cory J. Wesley's recurring snapshots of Oak Park Village Board agendas. Form-driven editor → live preview → HTML + PNG output → YAML-archived issues.

See `AGENDA_ENGINE_BRIEF.md` for the full build brief.

## Status

Pass 1 (skeleton). Flask app serves the May 12, 2026 reference render verbatim at `/`.

## Run locally

```sh
uv sync
uv run flask --app app run
```

Open <http://localhost:5000>.

## Layout

```
app.py                  Flask app
templates/
  snapshot.html.j2      The parameterized snapshot (currently a verbatim copy of the may12 reference)
static/
  assets/logo.png       Logo banner, extracted from the reference HTML's base64-embedded img
  editor.css            Editor chrome styles (placeholder)
agendas/                YAML archive (one file per issue) — gitignored
out/                    HTML + PNG renders — gitignored
```

## Reference renders

- `oak_park_agenda_wesley_may12_pressuretest.html` — Issue 03 (May 12, 2026). The authoritative styling source for the snapshot template.
- `oak_park_agenda_wesley_feb10_v7_masthead.html` — Issue 02 (Feb 10, 2026). Reference for Feature section structure only (its CSS is not used).
