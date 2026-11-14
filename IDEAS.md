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

## Detecting near-synonym pairs from real mistakes

Idea from 2026-11-09, sparked by actually typing щегольство for a card that
wanted фатство — two words whose English translations had drifted into
reading as pure duplicates, when they actually have a real distinction
(style-as-choice vs. vanity-as-character-flaw) that two sloppy translations
had papered over. Fixed that specific pair by hand, but the real question:
could Lexi *surface* candidates like this automatically, instead of
relying on noticing it by accident mid-review?

**Why this doesn't work today:** `check_answer()` in `review.py` only ever
uses the typed text ephemerally, to decide exact/close/wrong in the
moment — it's never written down anywhere. There's no log, so there's no
history to mine for "typed word Y when card X was the answer" patterns.
This would need new infrastructure, not just a query over existing data.

**Rough shape discussed:**
- Log each wrong/close attempt: the card's id, and the typed text —
  probably a simple append-only file (`mistakes.log`?), not bolted onto
  `vocab.json` itself, since this is session telemetry, not vocab data.
- The interesting signal isn't "got it wrong" generically — plenty of
  wrong answers are just blanks or genuine don't-knows. The real signal is
  specifically: **the typed text matches another real entry's `word`
  field** (ignoring case/accents), and it happens **more than once** for
  the same card. A single mix-up is noise; a repeated one across multiple
  review sessions is a real candidate — exactly how щегольство/фатство
  would have surfaced if this had existed already, since it happened more
  than once before getting noticed by hand.
- A lightweight analysis pass (not live/automatic) — something run
  on-demand, similar in spirit to how the career-agent's Market Signal Log
  works: scan the mistake log, group by (card id, confused-with id) pairs,
  surface ones crossing some repeat threshold (2+? 3+?) as candidates
  worth a human look — not auto-editing entries, since telling real
  distinctions apart (like this one turned out to have) needs actual
  judgment, not just statistics.

Not built. Revisit once there's been enough review volume since this idea
existed for the log to actually contain something worth mining — logging
from day one, even before the analysis step exists, so the data isn't
retroactively unavailable later.

## Images for concrete object words (clothing, tools, etc.)

Idea from 2026-11-03, sparked by кафтан — a word whose meaning is a
specific, unfamiliar physical object (a traditional belted Russian coat)
that a text definition can only approximate. A picture would do real work
here in a way it wouldn't for an abstract word or a verb.

**Which words would actually benefit — sharper criterion than "concrete
object," per Julia's own refinement:** not just any physical object word,
but specifically one where *even the English gloss* doesn't produce a
clear mental picture. "A coat" or "a shed" already paint a clear enough
picture once translated — no image needed. "A kaftan" doesn't clear that
bar even in English; that's the real signal, not concreteness alone. Some
candidates from recent reading likely pass this stricter bar (кафтан,
соха, цеп, чурбак — specific old tools/garments with no close everyday
English equivalent); some concrete-but-ordinary object words probably
don't (e.g. a plain доска, "board/plank," already pictures fine from the
English alone). Not abstract nouns, not verbs/adjectives, not idioms
either way — a picture doesn't add anything for "to persuade" or "fate."
This needs the same kind of judgment call already made for cultural_note
(not every word, only where it adds real value), likely even narrower —
something to add deliberately on request for a specific word, not
something the add-word skill tries to do automatically for every noun.

**Where would it show — a real open question, not just a UI detail:**
putting the image in the *prompt* itself (alongside the English
translation) changes what's being tested — recognizing an object visually
is a different, arguably easier recall path than translating English text,
and for objects this specific and unfamiliar, it might make the card too
easy to be a meaningful test. Putting it only in the *reveal* (after
answering, alongside cultural_note) keeps the actual recall test as-is and
treats the image purely as a memory aid/reinforcement, closer to how
cultural_note already works. Leans toward reveal-only, but worth deciding
deliberately rather than defaulting to "just add it wherever."

**The real cost is sourcing, not the schema change:** Lexi already has a
precedent for this — the README's two decorative images (rose, butterfly)
are specifically public-domain Wikimedia Commons scans, cropped locally,
credited in a dedicated README section. Each new vocab image would need
the same care: find a correct, actually-representative image (a modern
stock photo of "a coat" won't do for кафтан specifically — accuracy
matters more here than for decoration, since a misleading image actively
teaches the wrong thing), verify its license, download and prep it, credit
it. That's a real per-word content task, not a quick toggle — much closer
to writing a good cultural_note than flipping on a boolean field.

**Rough shape:**
- Schema: an optional `image` field per entry — local file path (checked
  into the repo, matching existing practice, not a hotlinked external URL
  that can rot) plus credit/license info, parallel to how the README
  tracks the two existing decorative images.
- UI: a conditionally-rendered `<img>` in the reveal section of both
  Write and Recognize modes, shown only when an entry has one.
- No automation planned — adding an image to a word is something Julia
  asks for explicitly, word by word, the same way "find me an article
  about this" already works as an on-demand request rather than a
  default step in the capture flow.

**Built 2026-11-14**, exactly to this shape: `image` + `image_credit`
fields, reveal-only (both modes), added one word at a time on request.
First four: шинель, тулуп, сюртук, картуз — specific Russian coats
and headwear Julia wanted visually disambiguated from each other
(and, for картуз, from a generic "a cap"). Credits in
the README's "Vocab-card images" section. Still no automation — adding
an image to a word remains an explicit, one-at-a-time request.

## Paradigm drills for high-frequency words (declension/conjugation fluency)

Idea from 2026-11-03, sparked by removing a demo word (день, added only to
show Dad how Lexi works) — a word like день doesn't need *vocabulary*
practice (its meaning is trivial), but a word that common genuinely does
deserve a different kind of practice: fluently producing its full
grammatical paradigm (день/дня/дню/день/днём/дне, singular and plural) on
demand. Same idea for high-frequency verb conjugation (я делаю/ты
делаешь/он делает/...). This is a meaningfully different skill than
recalling what a rare literary word means, and the current deck doesn't
drill it at all.

**Why this doesn't fit the existing vocab.json/Write-mode model, same
reasoning as the grammar-construction-drills idea above:** one vocab entry
= one word = one correct string to type. A paradigm isn't one answer, it's
up to 12 cells (6 cases × singular/plural for a noun) or ~6+ cells per
tense for a verb. Storing each inflected form as its own standalone
vocab.json entry would be bulky, and would reopen the same-root leak
problem systematically — every inflected form's English gloss would need
to carefully avoid revealing the lemma it's built from, for every single
cell, which doesn't scale.

**Also a different pedagogical goal than the rest of Lexi, worth being
honest about:** vocabulary entries are scheduled with SM-2 because the
risk is *forgetting* a word you don't encounter often. High-frequency
words are, by definition, encountered constantly — the actual goal here is
*automaticity* (producing the right form instantly, without conscious
effort) rather than fending off forgetting. That might mean this doesn't
want spaced-repetition scheduling at all — more like timed drilling
practice (closer to multiplication-table overlearning) than date-scheduled
review. Worth deciding deliberately rather than defaulting to "just reuse
SM-2" out of habit.

**Rough shape discussed:**
- A small, deliberately curated list of high-value words — NOT sourced
  from reading the way vocab.json is, but chosen specifically for real
  conversational frequency (common nouns like день, дом, рука; common
  verbs like быть, делать, идти, хотеть). Quality over quantity — this
  list should probably stay short and overlearned, not grow indefinitely.
- Each entry stores its full paradigm once (likely generated by Claude at
  add-time, same spirit as how definitions are written now, but verified
  against real forms rather than guessed — Russian has real irregularity,
  stress shift, and fleeting vowels that make rule-based generation
  unreliable to trust blindly).
- A review mode that picks a random word + a random cell from its
  paradigm (e.g. "день — instrumental plural?") and checks the typed
  answer — distinct from Write/Recognize mode, since the "question" varies
  per attempt even for the same word, unlike a normal vocab card.

**Connects to** the dual-aspect verb card idea above — both are about
drilling Russian morphology rather than word-meaning recall, and might end
up sharing infrastructure (a `paradigms.json`-style file, a dedicated
review mode) rather than being two separate features.

Not built. Revisit once there's appetite for a review mode that's
genuinely different in kind from Write/Recognize, not just a variation on
them.

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
