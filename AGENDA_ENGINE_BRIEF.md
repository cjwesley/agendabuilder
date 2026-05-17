# The Agenda — Build Brief

A solo-author publication engine for Trustee Cory J. Wesley's recurring snapshot of Oak Park Village Board agendas. Form-driven editor → live preview → HTML + PNG output → YAML-archived issues.

## Stack (locked)

| Concern | Choice | Why |
|---|---|---|
| Web framework | **Flask** | Single-user internal tool, server-rendered HTML, no SPA needed. |
| Live updates | **HTMX** | Debounced keyup → server re-render of preview pane. ~50 lines of JS-free interactivity. |
| Templates | **Jinja2** | Ships with Flask. The v11 reference HTML drops in directly as a parameterized template. |
| HTML→PNG | **Playwright (Chromium)** | Already validated working in the parent project. |
| Archive format | **YAML (PyYAML)** | One file per issue, diff-friendly, human-readable. |
| AI drafting | **Anthropic SDK** | First-draft section copy from agenda overviews. |
| Legistar | **httpx** | Direct REST calls to webapi.legistar.com. |
| Deploy | **Fly.io** | Single small machine + persistent volume for the YAML archive. |

## Project layout

```
agenda-engine/
├── app.py                     # Flask app: routes, form handling, HTMX endpoints
├── render.py                  # Jinja → HTML → Playwright → PNG
├── legistar.py                # Legistar API client
├── drafter.py                 # Claude API: first-draft generators
├── schema.py                  # Pydantic models for the issue data
├── templates/
│   ├── editor.html            # Two-pane: form (left) + preview iframe (right)
│   ├── snapshot.html.j2       # The v11 design, parameterized (drop-in)
│   └── partials/
│       ├── form_section.html  # Renders one section's form fields
│       └── preview_pane.html  # The HTMX target for live preview
├── static/
│   ├── editor.css             # Editor chrome only — snapshot styles are inline in snapshot.html.j2
│   └── editor.js              # Render-mode toggle, save state, settings
├── prompts/
│   ├── feature_draft.md       # System prompt for full-feature articles
│   ├── compact_draft.md       # System prompt for "Also on Regular" one-liners
│   └── voice_guide.md         # Editorial voice reference (loaded into every draft prompt)
├── agendas/                   # YAML archive (one per issue) — Fly volume mount
├── out/                       # PNG renders — Fly volume mount
├── assets/
│   └── logo.png               # The CJ Wesley brand banner
├── Dockerfile
├── fly.toml
├── pyproject.toml
└── README.md
```

## Editorial bucketing rules

The schema is plumbing for editorial decisions. These rules govern those decisions and are the source of consistency across issues. They apply when manually placing items, when reviewing AI-bucketed items, and when the Legistar import auto-buckets — Legistar's own section headings are a starting point, not an authority.

### The decision tree

For every item pulled from a meeting, walk this tree in order. Stop at the first match.

```
1. Is this item up for a vote?
   ├── Yes, and it's complex/policy-heavy ──→ § I Feature
   ├── Yes, and it's discrete/transactional ──→ § III Regular Compact
   └── No ──→ go to 2

2. Is it tied to a related vote elsewhere on the agenda?
   ├── Yes ──→ fold it INTO that feature in § I (no separate section)
   └── No ──→ go to 3

3. Is it substantively meaty — direction-setting, not procedural?
   ├── Yes ──→ § II Study Session
   └── No ──→ probably doesn't need a callout (consider omitting)
```

**Worked example from Issue 01:** ID 26-317 (Lead Service Line presentation) appears under "Regular Agenda" on the official Village agenda — but it has no vote of its own. Step 1: no vote → continue. Step 2: paired with RES 26-202 (the pilot vote) → fold into § I as part of the Lead Pipes feature. Even though Legistar bucketed it as Regular, the editorial decision was different.

### Per-section purpose

| § | Section | What goes here | Treatment |
|---|---|---|---|
| I | **Features** | Vote items that are complex policy. Multiple presentations can be combined into one feature when they pair with a vote. | 2-col layout (side label + body prose). Drop cap, optional pullquote. |
| II | **Study Sessions** | Items the Board will discuss but NOT vote on. Substantive direction-setting only. | Blue block. Most visually distinctive section. Reserved for items that genuinely shape future decisions. |
| III | **Regular Compact** | Vote items that are discrete or transactional. The boring-but-real votes that don't need a full feature. | Bordered card per item. Optional `note` field renders a one-line italic editorial frame below the description. |
| IV | **Consent Agenda** | Routine items packaged for a single vote. Strictly consent-only. | One-sentence summary (count + flag count + total dollars) followed by flagged items only with their notes. Routine items are counted, not listed. |
| V | **Civic Notes** | Proclamations, appointments, vacancies. The ceremonial and procedural tail of the meeting. | Masonry layout (`column-count: 2`). Each item is a self-contained block; blocks flow into 2 columns by height to balance the section. Reorder items in the YAML so shorter blocks are willing to "fall up" into gaps below taller blocks. |

### Cross-cutting rules

1. **Empty sections are omitted entirely.** A meeting with no Study Sessions has no § II — and § III becomes the new § II via auto-renumbering. Section numbering is computed at render time from the list of present sections, never hardcoded.
2. **Multiple items per section is the norm, not the exception.** § I supports multiple features stacked. § II supports multiple Study Session blocks stacked with a small gap. § III is a list of cards. § IV is a list of rows. § V's proclamations list grows with content. Don't optimize for the single-item case — optimize for 2-4 items per section.
3. **Consent never mixes with regular.** Even one regular item gets its own § III. Even one consent item gets its own § IV. The editorial signal "this is routine" depends on the section boundary holding.
4. **Consent renders as summary + flagged items only.** The full agenda is one click away — the snapshot doesn't reproduce it. The consent section consists of:
   - **A one-sentence summary** stating: total item count, count of flagged items, and a single combined dollar figure (`"Four items flagged below for a second look. 9 additional routine items packaged for a single vote — $1.43M total in financial commitments."`). The dollar figure sums all `cost` fields across all consent items, regardless of flag status. Currency formatting collapses to `$X.XXM` for clarity.
   - **The flagged items**, each with their `why_it_matters` note. The flag (★), title, Legistar ID, and one-line italic note are the only visual elements. No per-item costs in the rendered list (they appear in titles where editorially relevant, e.g., "Granicus subscription expansion — $179,489.65 / year").
   - Routine items are not listed individually. They're counted in the summary line and that's it.
   
   This is a deliberate inversion of comprehensiveness. Consent items don't get discussed; the snapshot shouldn't pretend they're worth a row each.

5. **Consent item titles must fit on a single line at 1080px width.** Hard limit: roughly 80 characters. The renderer's tight line-height assumes one-line titles; wrapping breaks the visual rhythm. Editor UI shows a character counter and warns at 75 characters. AI drafter is prompted to stay under 70.

6. **Editorial flag is for significance, not cost.** The flag (★) is for multi-year governance commitments, policy precedent, contested ratifications — items where a reader genuinely benefits from a second look. A large cost number alone is not a flag. Routine procurements stay routine regardless of dollar amount.
7. **Items that don't fit anywhere go to "Triage."** When Legistar import or AI bucketing can't confidently place an item — Public Hearings, First/Second Readings, ambiguous resolutions — it lands in a Triage drawer in the editor for manual placement. Better to surface ambiguity than guess wrong.
8. **Headlines are 2 or 3, never 4+.** Three is the default and most issues support it. When a third slot has no obvious candidate, the cell uses a `process_note` treatment — same visual cell, but with a short prose statement instead of a figure (e.g., "No major votes this meeting" or "Light agenda — three study sessions"). Reaching for a weak third headline is worse than acknowledging a quiet meeting. See the **Headlines** section below for slot definitions and selection logic.

9. **Counts always go in eyebrows or labels, never in titles.** Section titles ("Consent Agenda", "Civic Notes") and block labels ("Proclamations", "Appointments") must be content-agnostic. Counts that vary issue-to-issue go in eyebrows under section titles, or as the value-bearing line inside a block. **Wrong:** "Three Study Sessions" as a section title. **Right:** title "Study Sessions" + eyebrow "3 items · Discussion · No votes". The renderer computes counts at render time; the editor doesn't manage them.

### Headlines

The three stat cards at the top of the snapshot are the TL;DR. They're the first thing readers see and often the only thing they read.

**Slot definitions:**

| Slot | Purpose | Typical content |
|---|---|---|
| **The Big Number** | The single most consequential figure in the meeting — what makes residents care | A dollar amount, a metric, a count that signals scale |
| **On the Table** | What the Board is choosing tonight | A count of votes, a specific decision (address, entity name), or count of items in a contested section |
| **For the Calendar** | Forward-looking civic items | Proclamation count, vacancy count, scheduled events |

**The Big Number is editor-selected, not algorithmic.** The agenda metadata does not reliably surface the most consequential number. The right Big Number is often buried in a staff memo's background section — like a Pavement Condition Index of 66 inside a discussion of funding scenarios. An AI drafter pulling structured Legistar fields won't find it; an editor reading the source document will. The engine *suggests*; the editor *decides*.

The other two slots are more amenable to algorithmic defaults but still take editor override.

**Per-slot recommendation logic** (the engine ranks candidates for each slot independently):

| Slot | Ranked suggestion sources |
|---|---|
| The Big Number | (1) Largest dollar amount in any feature vote; (2) Largest dollar in any vote including consent; (3) Count of high-attention items (features, study sessions). **Editor knows best — override expected.** |
| On the Table | (1) Count of regular agenda items; (2) Count of feature articles; (3) A specific decision when one item dominates (the address being acquired, the entity being renamed). |
| For the Calendar | (1) Proclamation count; (2) Vacancy count; (3) Count of upcoming events referenced in any item. |

**Editor UX.** Each headline slot in the form has three controls:

1. **Suggestion picker** — a dropdown of 4-8 ranked candidates for that specific slot, sourced from the Legistar pull. Selecting populates the figure/caption with reasonable defaults.
2. **Free-text figure + caption fields** — always editable, with character-count guardrails per the Content Guardrails table. Override is the default mode; suggestions are an aid.
3. **Optional source field** — a short citation pointing to where the number came from (e.g., "Pavement Management Program, ID 26-320 — staff memo background"). Not rendered on the snapshot; lives in the YAML for archive and audit.

**Schema:**

```yaml
headlines:
  - slot: big_number               # required: big_number | on_the_table | for_the_calendar
    kicker: "The Big Number"       # the small label above the figure
    figure: "66"                   # the rendered value
    caption: "Oak Park's Pavement Condition Index — a grade for the road network. Tonight's session debates whether to hold there or push higher."
    source: "ID 26-320 — staff memo background"   # optional, not rendered
  - slot: on_the_table
    kicker: "On the Table"
    figure: "1"
    caption: "The single Regular Agenda vote tonight — a cohousing escrow waiver."
  - slot: for_the_calendar
    kicker: "For the Calendar"
    figure: "4"
    caption: "May proclamations: Public Works Week, Older Americans, APIDA Heritage, Jewish American Heritage."
```

**Process-note fallback** (used when there's no good third headline):

```yaml
  - slot: for_the_calendar
    kicker: "Note"
    process_note: "Light agenda — three study sessions and no major votes."
    # When process_note is present, figure/caption are ignored
```



The Jinja template iterates a `present_sections` list, not a fixed § I → § V scaffold. Each entry in the list carries its own `kind`, `items`, and a runtime-assigned `roman_numeral`. Section partials (`feature.html.j2`, `study.html.j2`, etc.) are dispatched on `kind`. Adding a new section type later (a "Public Hearing Watch" block, say) means a new partial + a new bucketing rule, not a template rewrite.

## Data model

The YAML schema. One file per issue, named `agendas/{YYYY-MM-DD}.yaml` matching the meeting date.

```yaml
issue:
  number: 1
  meeting_date: 2026-05-05      # ISO date — drives filename, masthead, validation
  meeting_time: "7:00 PM"
  meeting_date_short: "Tuesday, May 5"   # human label for footer 2x2 grid
  location: "Village Hall · Council Chambers, Room 201"   # combined; street omitted
  agenda_url: "https://www.oak-park.us/Government/Meetings/Village-Board-Agendas-Minutes-Videos"
  clerk_email: "clerkwaters@oak-park.us"
  public_comment_email: "publiccomment@oak-park.us"   # different from clerk_email
  public_comment_phone: "708-358-5670"

masthead:
  tagline: "A curated guide to the upcoming Board meeting"
  subtitle: "A reader's guide to the May 5 Village Board meeting — the water bill, the lead pipes, the special events, and four proclamations for the month."

headlines:                       # exactly 3
  - kicker: "The Big Number"
    figure: "$607,500"
    caption: "Proposed budget amendment for a 2026 lead service line replacement pilot — financed as low-interest loans on water bills."
  - kicker: "On the Table"
    figure: "3"
    caption: "Water & sewer rate-design alternatives presented by NewGen Strategies. The choice will shape bills through 2030."
  - kicker: "For the Calendar"
    figure: "4"
    caption: "Proclamations on deck: Mental Health, Small Business Week, Foster Care, Public Service & Building Safety."

sections:
  - kind: feature
    num: "I"
    title: "Lead, Pipes & the Price of Water"
    eyebrow: "Two presentations · One pilot vote"
    articles:
      - tag: "The Lead Service Line Question"
        headline: "A federal mandate, an Illinois law, and a bill that has to land somewhere."
        legistar_ids: ["ID 26-317", "RES 26-202"]
        body_md: |
          The federal Lead and Copper Rule Improvements...

          The companion resolution proposes a **2026 pilot program**...
        pullquote:
          label: "From the staff proposal"
          text: "A pilot program targeting properties impacted..."

  - kind: study
    num: "II"
    title: "A Closer Look at Special Events"
    eyebrow: "Study session · No vote"
    tag: "Working Session"
    headline: "How does Oak Park host its festivals, runs and block parties — and what's working?"
    body: "Staff will present an overview..."
    legistar_ids: ["ID 26-185"]

  - kind: regular_compact          # replaces the mixed "Also on the Agenda"
    title: "Also on the Regular Agenda"
    items:
      - name: "Bayan Ceramics — 222 Lake Street"
        text: "Cook County Class 7C tax incentive for a woman- and minority-owned ceramics studio & education center."
        legistar_ids: ["ORD 26-136"]
        flag: false                # ★ marker + reserved for editorial note
        why_it_matters: ""         # only rendered if flag: true
        note: ""                   # optional one-line italic editorial frame below the description.
                                   # Use when an item deserves contextual framing but doesn't merit
                                   # a feature. Different from why_it_matters (which is for flagged
                                   # consent items). Renders as small italic; no ★ marker.

  - kind: consent                  # strictly consent-only; renders as summary + flagged items
    title: "Consent Agenda"
    eyebrow: "13 items · No discussion"   # auto-generated as "{count} items · No discussion"
    items:
      # Field reference:
      #   name           string (required, ≤ 80 chars) — short item description; embed cost in title if relevant
      #                  HARD limit: must fit on one line at 1080px; renderer's line-height assumes single-line titles
      #   legistar_ids   list[string] (required)
      #   flag           bool (default false) — editorial significance; only flagged items render individually
      #   why_it_matters string (required if flag: true) — one-sentence note
      #   cost           number | null (default null) — contributes to the summary total; not rendered per-item

      # Flagged items render as rows with their why_it_matters notes
      - name: "Police Lieutenants & Sergeants CBA — January 2026 through December 2028"
        legistar_ids: ["RES 26-135"]
        flag: true
        why_it_matters: "A successor collective bargaining agreement covering Police Sergeants, plus a side letter on referral incentives. A multi-year labor commitment, locked in tonight."
      - name: "Granicus subscription expansion — $179,489.65 / year"
        legistar_ids: ["RES 26-129"]
        cost: 179489.65
        flag: true
        why_it_matters: "A recurring annual commitment, not a one-time buy."

      # Unflagged items contribute to count + total only; not rendered individually
      - name: "Sale of surplus Village vehicles & equipment"
        legistar_ids: ["ORD 26-111"]
      - name: "Sewer Jetter truck replacement"
        legistar_ids: ["RES 26-133"]
        cost: 549551.49
      # ... (remaining routine items)

  - kind: civic_notes              # renders as 2-column masonry; YAML order = column flow order
    title: "Civic Notes"
    # Order matters: shortest-but-meaningful first. The renderer flows blocks into 2 columns
    # by height. With sparse proclamations, vacancies floats up under it in column 1.
    proclamations:                 # tight one-line list within its block
      - name: "Mental Health Awareness Month"
        when: "May 2026"
        legistar_ids: ["MOT 26-157"]
      - name: "National Small Business Week"
        when: "May 3 – 9"
        legistar_ids: ["MOT 26-158"]
    vacancies:                     # always short — list 2nd so it falls up into gaps
      count: 23
      body: "Across the Village's 18 citizen boards and commissions — applications via the Clerk's Office."
      legistar_ids: ["ID 26-325"]
    appointments:                  # often the tallest block — list last
      - body: "Mark D. Johnson to the Board of Health; Stephen F. Smith to the Citizens Police Oversight Committee."
        legistar_ids: ["MOT 26-160"]
```

### Three structural rules baked into the template

1. **`regular_compact` and `consent` never share a section.** Schema enforces — no shared `kind`.
2. **Consent renders as summary + flagged items only.** No per-item rows for routine items. See cross-cutting rule 4 above for the format. Routine items contribute to the count and dollar total in the summary line; they do not appear individually.
3. **`flag: true` adds a `★`** marker and renders the `why_it_matters` line as a single-sentence inline note. Flag is for editorial significance only — see cross-cutting rule 6. Title length is capped at ~80 chars per cross-cutting rule 5.

### Civic Notes: masonry, not fixed cells

Civic Notes is rendered as a CSS `column-count: 2` masonry. Each `proclamations`, `appointments`, and `vacancies` block becomes a self-contained `.civic-block` with `break-inside: avoid`. The browser flows blocks into two columns top-to-bottom, balancing by height.

**Block ordering matters.** The YAML's order is the column-flow order. To get a balanced render, list blocks shortest-but-meaningful-first, with the tallest block last. Recommended default order:
1. Proclamations (variable height — usually 1-4 items)
2. Vacancies (always short — one paragraph)
3. Appointments (often the tallest block when there are 4+ appointees)

This ordering means: when proclamations are sparse, vacancies floats up under it in column 1, leaving appointments to take column 2. When proclamations are dense, vacancies and appointments share column 2.

Proclamations themselves are still rendered as a tight one-line list within their block (no 2x2 cards).

### Footer composition

The footer is a single dark band — three panels, no separate "speak" + "editors-note" sections, no vertical stacking. Replaces the previous design's separate speak block + editors-note block.

**Three panels in a single row, fr-ratio `1.2 : 1 : 1.4`:**

1. **Public comment** (1.2fr — left)
2. **Meeting details** (1fr — center)
3. **Editor's note** (1.4fr — right, signature included)

**Per-panel content:**

| Panel | Label treatment | Body |
|---|---|---|
| Public comment | Italic serif headline ("Make your voice heard.") at 14px — distinctive treatment for the only emotionally-active panel | Compressed paraphrase of the agenda's verbatim public-comment language — covers the 5pm deadline, phone, email, camera-on rule, three-minute limit |
| Meeting details | Sans caps eyebrow ("MEETING DETAILS") at 10px — standard panel label | 2×2 grid: top row = `Date | Time` as scannable peers, bottom row = `Village Hall · Council Chambers` (full width, separated by thin rule). No field labels — values speak for themselves. Street address omitted (Village Hall is googleable; the masthead carries it once already) |
| Editor's note | Sans caps eyebrow ("EDITOR'S NOTE") at 10px — standard panel label | The disclosure language ("not an official Village communication"), the agenda-packet link, and the highlighted-WESLEY signature on its own line at the bottom |

**Why one panel uses italic serif while the other two use sans caps:** the public-comment panel is the only call-to-action in the footer. The other two are utility (where/when, disclaimer). Mixing the typographic register *intentionally* — italic serif at 14px sits at roughly the same visual weight as 10px sans caps, but reads as a different kind of label. The reader's eye registers "this panel is doing different work."

If the editorial register feels too varied, fall back to all-three-panels-uniform (use the sans caps eyebrow on all three, drop "Make your voice heard." entirely or relegate it to body copy). The italic-serif treatment is a deliberate accent, not a structural requirement.


## The editor

Two-pane layout. Form on the left, preview iframe on the right.

```
┌─────────────────────────┬─────────────────────────────┐
│ Issue meta              │                             │
│ Masthead                │                             │
│ Headlines (×3)          │                             │
│ ─────────────────────   │   <iframe                   │
│ § I — Feature           │     src="/preview"          │
│   Article 1             │     hx-target="self">       │
│   + Add article         │                             │
│ § II — Study session    │   (renders snapshot.html.j2 │
│ § III — Regular compact │    with current form state) │
│ § IV — Consent          │                             │
│ § V — Civic notes       │                             │
│ ─────────────────────   │                             │
│ [Render mode toggle]    │                             │
│ [Pull from Legistar]    │                             │
│ [Draft with AI]         │                             │
│ [Save] [Export PNG]     │                             │
└─────────────────────────┴─────────────────────────────┘
```

### Live preview

- Form posts to `/preview` on every input change with HTMX:
  ```html
  hx-post="/preview"
  hx-trigger="keyup changed delay:300ms, change"
  hx-target="#preview-iframe"
  hx-swap="outerHTML"
  ```
- The toggle flips `hx-trigger` between `keyup changed delay:300ms` (live) and `click from:#render-button` (manual). Setting persists via `localStorage`.
- The 300ms debounce prevents request thrashing on every keystroke.

### Render mode toggle

Top-right of the form pane:

```
○ Live preview     ● Manual render
```

Persisted in localStorage. Default is **Live**.

### Content guardrails

Form fields with hard length limits show a live character counter and warn before the limit:

| Field | Soft warn | Hard limit | Why |
|---|---|---|---|
| `consent.items[].name` | 75 chars | 80 chars | Must fit on one line at render width; the consent row uses a tight line-height that assumes single-line titles. Wrapping breaks visual rhythm. |
| `headlines[].figure` | 8 chars | 12 chars | Renders at 50px; longer figures overflow the cell. |
| `headlines[].caption` | 110 chars | 140 chars | Cell has bounded width; longer captions push the headlines block taller and break the grid. |
| `feature.headline` | 90 chars | 120 chars | Renders at 28px; longer headlines wrap to 4+ lines and unbalance the feature layout. |

The AI drafter is prompted to stay under the soft warn for each field. The editor doesn't block on hard limits — it warns visibly and lets the user decide. Hard limits are about the render breaking, not editorial taste.

## Legistar integration

Oak Park is a Granicus/Legistar customer. The webapi is unauthenticated for read.

### Identifying Oak Park's client name

Try in order: `oakpark`, `villageofoakpark`, `oak-park`. Whichever returns 200 on `/v1/{client}/Bodies` wins. Persist as `LEGISTAR_CLIENT` env var.

### Endpoints used

```
GET https://webapi.legistar.com/v1/{client}/Bodies
  → find the BodyId for "President and Board of Trustees"

GET https://webapi.legistar.com/v1/{client}/Events
  ?$filter=EventBodyId eq {body_id}
  ?$orderby=EventDate desc
  → list of meetings

GET https://webapi.legistar.com/v1/{client}/Events/{EventId}/EventItems
  ?$expand=EventItemMatterAttachments
  → all agenda items for one meeting
```

### Data mapping

Each `EventItem` has fields we map directly:

| Legistar field | YAML field |
|---|---|
| `EventItemMatterFile` | `legistar_ids[]` (e.g., `MOT 26-155`) |
| `EventItemTitle` | initial `name` (user usually rewrites) |
| `EventItemMatterType` | hint for kind: `Motion` → consent likely, `Resolution` → consent or regular, `Discussion Item` → study/feature |
| `EventItemAgendaSection` | the agenda section heading from the official PDF — drives initial bucketing |

### Bucketing logic on import

Legistar's `EventItemAgendaSection` is a **starting suggestion**, not the final placement. The editorial decision tree (see Editorial bucketing rules above) is authoritative. The import maps Legistar's bucket to a *first-pass* placement; the editor reviews and re-buckets where the editorial logic differs.

| Legistar `EventItemAgendaSection` | First-pass placement |
|---|---|
| "Consent Agenda" | § IV Consent (default) |
| "Regular Agenda" | § III Regular Compact (user often promotes to § I Feature) |
| "Proclamation" | § V Civic Notes → proclamations |
| "Citizen Commission Appointments" | § V Civic Notes → appointments |
| "Citizen Commission Vacancies" | § V Civic Notes → vacancies |
| "Public Hearing" / "First Reading" / "Second Reading" | **Triage** — editor decides |
| Anything else / unrecognized | **Triage** |

**Why Triage exists.** Many items don't have an obvious editorial home. A First Reading might be a quiet placeholder or a major rezoning — the import can't tell. Forcing the editor to make a deliberate placement on ambiguous items is more honest than guessing.

**Promotion is the common edit.** Items Legistar tags "Regular Agenda" frequently belong in § I as a Feature (with a paired presentation folded in) rather than § III. The editor UI should make promote-to-feature a single click.

### Pull workflow

1. User clicks **Pull from Legistar** button
2. Form shows date picker / list of upcoming meetings
3. User picks one
4. App fetches event items, applies default bucketing, populates form
5. User reviews, promotes/demotes items between sections, edits copy

## AI first-draft generation

Each `feature` article and `study` section gets a **Draft with AI** button. Click sends:

- The system prompt from `prompts/feature_draft.md` or `prompts/study_draft.md`
- Voice guide content from `prompts/voice_guide.md`
- The Legistar `EventItemTitle` + any agenda overview text scraped from the linked staff report PDF

Returns: a draft of `headline`, `body_md`, and (for features) a `pullquote` candidate. User reviews and edits in the form.

### Voice guide content (drop into `prompts/voice_guide.md`)

```markdown
# Editorial voice for The Agenda

- Declarative. Prose, not bullet points.
- Specific over abstract: dollar amounts, dates, statute names, mechanics.
- Slightly literary headlines that capture the actual stakes ("A federal mandate, an Illinois law, and a bill that has to land somewhere") — never generic ("Lead service line update").
- Body copy explains the policy mechanism, not the political conflict.
- Pullquotes lift a single sentence from the staff report or memo, never editorial commentary.
- Translate jargon ("Translation: ...") when the agenda language is opaque.
- Short paragraphs. 2–3 sentences each. Never longer than 4.
- Em dashes are preferred over parentheses or semicolons.
```

### Model choice

Default to `claude-opus-4-7` (per current product knowledge) for drafting. Model name configurable in `.env`.

## Render pipeline

```python
def render_issue(issue_yaml_path: str) -> tuple[Path, Path]:
    issue = load_yaml(issue_yaml_path)
    html = jinja_env.get_template("snapshot.html.j2").render(**issue)

    html_out = OUT_DIR / f"{issue['issue']['meeting_date']}.html"
    png_out  = OUT_DIR / f"{issue['issue']['meeting_date']}.png"

    html_out.write_text(html)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1080, "height": 1600},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(f"file://{html_out}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=png_out, full_page=True)
        browser.close()

    return html_out, png_out
```

## Fly.io deployment

### Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
COPY pyproject.toml uv.lock* /app/
RUN pip install uv && uv sync --frozen

COPY . /app

EXPOSE 8080
CMD ["uv", "run", "gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
```

### fly.toml

```toml
app = "agenda-engine"
primary_region = "ord"

[build]

[mounts]
  source = "agenda_data"
  destination = "/app/agendas"

[mounts]
  source = "agenda_renders"
  destination = "/app/out"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 1024
```

Auto-stop when idle keeps Fly costs near $0.

### Secrets

```
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set LEGISTAR_CLIENT=oakpark
fly secrets set BASIC_AUTH_USER=cory
fly secrets set BASIC_AUTH_PASS=<redacted>
```

Basic auth on all routes — simplest single-user lock.

## v1 scope

**In:**
- Form editor with live preview
- Legistar pull + auto-bucketing
- AI first-draft per feature/study
- HTML + PNG render
- YAML archive
- Fly deploy with basic auth
- Render-mode toggle (live / manual)

**Out (deferred to v2):**
- Multi-user / co-editor
- Real auth (OAuth, etc.)
- Social-post generator
- Email or RSS distribution
- Auto-publish to web
- Analytics

## Reference files

`oak_park_agenda_wesley_feb10_v11_final.html` is the design ground truth. Drop it into `templates/snapshot.html.j2` and parameterize using the YAML schema above. Logo banner is base64-embedded; extract to `assets/logo.png` and reference via Jinja.

**Two reference renders** to validate the template against:

- `oak_park_agenda_wesley_v7_2026-05-05.html` — Issue 01 (May 5, 2026). Light agenda: 2 features paired with one feature having a paired study session, 1 regular item, 3 routine consent items, 4 proclamations, 1 appointment block, 1 vacancies block. Tests sparse content rendering.
- `oak_park_agenda_wesley_feb10_v11_final.html` — Issue 02 (Feb 10, 2026). Heavy agenda: 2 features, 1 regular item with paired ordinances, 13 consent items (4 flagged), 1 proclamation, 4 appointments, 1 vacancies block. Tests heavy consent + Civic Notes masonry behavior.

Both pages share the same template — the second is just longer. Use them as fixtures for the renderer's test suite: parameterize each, render to PNG, byte-compare against the references (or pixel-diff with a small tolerance for font-rendering noise across environments).

### Design decisions worth preserving

A few choices accumulated through iteration that aren't immediately obvious from the markup. Don't accidentally refactor these away:

- **Cream paper (`#f6f1e6`) with subtle dot grain.** Reads as editorial, not corporate. White paper looks like a Word document; cream looks like a publication.
- **Single-column flow above 1080px.** A 2-column experiment was run and rejected — column-balance problems on variable agenda volumes outweigh the space savings.
- **Civic Notes masonry over fixed grid.** Solves the asymmetry problem when proclamations are sparse. Block ordering in YAML drives column flow.
- **Italic-serif first panel label in footer.** Deliberate accent on the only call-to-action panel. The other two use sans caps. If this feels too varied for a given issue, all three can fall back to sans caps without breaking layout.
- **WESLEY signature highlight uses the same `linear-gradient` treatment as bolded body text.** Pink-soft highlight under the bottom 40% of the caps. A handwritten brush stroke was tried and rejected as too informal.
- **Consent renders as summary + flagged items only.** Routine items are counted, not listed. The full agenda is one click away — the snapshot doesn't reproduce it.
- **The Big Number is editor-selected, not algorithmic.** The most consequential figure in a meeting is usually buried in a staff memo's background — a Pavement Condition Index of 66, a vacancy count, a 21-month minutes backlog. The engine suggests; the editor decides. Don't refactor toward "auto-pick the biggest dollar amount" — that loses the editorial work that makes the snapshot worth reading.

## Suggested build order

Each pass should leave the app running.

1. **Skeleton.** Flask + Jinja + the v11 HTML hardcoded as the index route. Run, see it render in the browser.
2. **Parameterize.** Extract the YAML schema. Replace hardcoded values with `{{ issue.meta.* }}`. Hardcode a sample YAML. Render must match the v11 reference within ~1px tolerance.
3. **Form editor.** Build the left-pane form that reads/writes the same YAML. Submit posts to `/save`. No live preview yet.
4. **Live preview.** Add HTMX + the `/preview` endpoint. Add render-mode toggle.
5. **Render pipeline.** Add `/render` button → Playwright → PNG. Show in `/out` directory.
6. **Legistar pull.** Implement `legistar.py`. Add the Pull button + bucketing logic.
7. **AI drafting.** Implement `drafter.py` with the prompts. Add Draft buttons per section.
8. **Fly deploy.** Dockerfile + fly.toml + secrets. Deploy. Verify.

Each step is independently testable. Each commit should leave the app working.
