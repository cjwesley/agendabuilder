# Feature article — drafting instructions

A Feature is a 2–4 paragraph spotlight on a single substantive item, with a
literary headline, a short tag, and an optional pullquote pulled from the
staff overview.

## Length budgets

- **headline** — 70–110 chars; one sentence; ends with a period; landing on
  a specific mechanism or constituency, not a thesis statement.
- **tag** — 2–5 words; the *thematic* label for the spotlight
  ("Housing on Madison Street", "Police HQ + Village Hall"). Title-case.
- **body_md** — markdown. 2–4 paragraphs, 60–120 words each. Use `**bold**`
  to highlight 1–3 key noun phrases per article (a partner organization, a
  dollar figure, a constituency). Don't bold whole sentences. The first
  paragraph carries the drop cap — make it count.
- **pullquote_label** — short label like "From the staff overview" or
  "From the project description" (2–6 words). Title-case.
- **pullquote_text** — a verbatim or lightly trimmed quote from the source
  material that crystallizes the item, 1–2 sentences. If no quotable text
  is available, return an empty string for both pullquote fields.

## What to write about

- The **policy mechanism** — what is being voted on, in what order, and what
  the dependencies are between motions.
- The **dollar figure** if any, in context (FY budget, scale).
- The **counterparty** — the developer, contractor, agency, applicant.
- The **next step** if the vote passes (downstream design contract, public
  hearing, budget amendment).
- Where helpful, a one-sentence "translation" of what tonight's decision
  actually locks in.

## What to avoid

- Don't editorialize on whether the vote is good or bad — only on what it
  does.
- Don't speculate beyond what the source material supports.
- Don't pad with civic-process throat-clearing ("The Board will discuss…").
  Get to the substance.
