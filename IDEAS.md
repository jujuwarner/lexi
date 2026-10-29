# Future ideas (not built yet)

## Grammar construction drills (separate from vocab.json)

Idea from 2026-09-19: a way to capture and practice recurring *grammatical
constructions/patterns* (e.g. the literary double-negative "il n'y avait pas
de X... qui ne + verbe" = "there wasn't an X that didn't...", meaning "every
X did...") — distinct from single-word vocabulary.

Why it doesn't fit `vocab.json`/Write mode as-is: Write mode tests "see the
English, type the exact target-language word from memory." A construction
has no single correct string to type — it's a pattern applied to varying
content each time. Forcing it into that schema would just test whether the
abstract pattern label was memorized, not whether the construction is
actually recognized/usable in context.

Rough shape discussed:
- A separate file (`constructions.json`?) — pattern name, plain-English
  explanation, an explanation in the target language too, one or more real
  example sentences (pulled from reading), source, and its own SM-2 `srs`
  block so it can reuse the existing spaced-repetition scheduling.
- A new review mode (not Write mode) — show an example sentence, ask the
  user to recognize/explain what's happening grammatically, then self-rate
  like Recognize mode already does. No typing-the-answer mechanic, since
  there's no single right string.

**Open idea to explore when building this:** instead of only replaying the
same static example sentences saved at capture time, could new example
sentences be *generated* fresh each review (via LLM) using the saved
pattern + explanation as the spec? Would keep drills from going stale on
repeat exposure to the same 1-2 examples, and could probe whether the
pattern is genuinely understood rather than just pattern-matched against a
memorized example. Needs thought on: how to keep generated examples at the
right difficulty/vocab level, and how confident the check-the-comprehension
step can be over a freshly generated (not human-verified) sentence.

Not built. Revisit when there's a real backlog of captured constructions
worth a dedicated review mode.

## Algorithm-side weighting for niche-tagged words

Idea from 2026-09-19, paired with a simpler fix already shipped: entries
tagged `archaic`/`rare`/`technical` now get a delayed starting `next_review`
(14 days out instead of immediate) — see the add-word SKILL.md for the
data-only version of this. That only affects the *first* time a card
surfaces, though — once it's been reviewed once, it competes in the normal
SM-2 rotation exactly like everyday vocabulary from then on.

A deeper version of this idea: give niche-tagged cards an ongoing lower
"weight" in the review queue permanently, not just a one-time delay — e.g.
skip them some fraction of the time even when due, or bias due-card
selection so untagged everyday words are shown first when both are due on
the same day. Would need actual changes to `due_today()`/`run_review()` in
`review.py` (not just data), and a decision about whether this should be
automatic based on tags or something Julia can toggle per review session
(similar to the language picker, which only prompts when genuinely
relevant).

Not built. Revisit if the one-time delay from the data-only fix stops
feeling like enough — e.g. if niche words still end up cluttering reviews
regularly once they've been through their first cycle.

## Review metrics / stats view

Idea from 2026-09-20: some kind of visible metrics/stats display, at two
scopes:

- **Per-session** — how a given day's review session went: cards reviewed,
  accuracy (exact/close/wrong breakdown), maybe time spent.
- **Over time** — longitudinal view: total vocab size and its growth,
  review streak, retention trends (are older cards holding up at longer
  intervals, or getting missed and reset a lot), maybe a breakdown by
  language once there's enough Russian volume to make that interesting.

Data's already there for most of this — every entry's `srs` block has
`repetitions`, `easiness`, `interval`, `last_reviewed`, so a lot of this
could be computed by scanning `vocab.json` rather than needing new stored
state, though session-level stats (today's accuracy) would need something
to track "reviewed just now" beyond what a single entry's `srs` block
already holds after the fact.

Not built. No urgency signaled — just wanted it on record so it isn't
forgotten. Revisit whenever there's appetite for a small UI addition (a
stats page/section in the web UI) rather than treating it as a priority.
