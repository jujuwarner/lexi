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

## Dual-aspect verb cards (Russian imperfective/perfective pairs)

Idea from 2026-11-02: most Russian verbs come in aspect pairs — imperfective
(ongoing/habitual/repeated) and perfective (a single completed action) —
e.g. писать/написать, делать/сделать, закладывать/заложить. Right now
`vocab.json` stores one `word` per entry, so adding a verb means picking a
side. In practice this has already been handled inconsistently: some pairs
got split into two separate standalone entries (`закладывать лошадей` and
`заложить лошадей` are two different ids, cross-referenced only via a
`cultural_note` mentioning the other), while others only ever captured one
aspect (`сватать`, with `посватать` mentioned in passing in the note but
never actually practiced as its own recall target). Neither is a real
solution — the first means the pair is scheduled independently by SM-2 and
can drift apart (one well-known, one forgotten); the second just drops half
the verb's real usage.

**The actual idea:** for verbs where both aspects are genuinely common and
naturally used (not every verb pair qualifies — some perfective/imperfective
counterparts are rare or stylistically marked, and this doesn't apply at all
to idioms/fixed phrases where only one aspect ever makes sense, e.g.
"аза в глаза не видать"), test *both* forms as one card: one prompt, two
blanks to fill in (imperfective + perfective), checked and scheduled
together rather than as two independent entries competing separately for
review slots.

**Open design questions, not resolved yet:**
- **Schema**: would need an optional structure replacing the single `word`
  string for verbs that qualify — something like
  `"word": {"imperfective": "закладывать", "perfective": "заложить"}` —
  without breaking every other entry's assumption that `word` is a plain
  string. `display_word()`, `check_answer()`, and the web UI's prompt
  rendering would all need to branch on whether `word` is a string or this
  richer shape.
- **Review mechanic**: Write mode would need two input fields on one
  screen instead of one, both submitted together. Scoring gets genuinely
  tricky — what counts as "exact" if one form is typed perfectly and the
  other is wrong, or close? Probably needs its own three-way outcome
  (both right / one right / neither), analogous to how accent typos and
  missing articles already get a softer "close" bucket rather than a flat
  right/wrong.
- **One SM-2 history, not two**: the pair should share a single `srs` block
  (one scheduling history, one `next_review` date) rather than the current
  ad-hoc split into two independently-scheduled entries — that's the whole
  point of the idea, so this isn't optional if it's going to actually solve
  the problem the current workaround has.
- **Add-word-time judgment call**: the skill would need a new question at
  capture time, in the same spirit as the existing rare/archaic/technical
  flagging — "does this verb have a natural, equally common aspectual
  partner, and is this a plain verb rather than a fixed phrase?" — before
  deciding whether to prompt for both forms or just one.
- **Migration**: the existing split pairs already in `vocab.json` (at least
  закладывать/заложить лошадей) would need a decision — merge them
  retroactively into one dual-aspect entry, or leave existing entries as
  they are and only apply the new shape going forward.

Not built. Revisit when there's either a slow week with appetite for a
schema change, or when enough new verb pairs have been added the old
ad-hoc way that the inconsistency starts actively bothering review
sessions.

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
