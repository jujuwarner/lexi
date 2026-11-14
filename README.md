# Lexi

A personal spaced-repetition vocabulary tool for language learning — built to
replace a Quizlet habit with something that actually fits how I read and
study.

## Why this exists

Most flashcard apps make you stop reading, open the app, and manually build a
card before you can keep going — enough friction that new words often just
don't get captured. Lexi is built around the opposite workflow: while I'm
reading, I tell Claude the word and the sentence I found it in, Claude writes
the definition, and it's saved. No context-switching, no manual card-building.

Review happens separately, on my own schedule, using a real implementation of
the SM-2 spaced-repetition algorithm (the same algorithm behind Anki).

## How it works

**Adding words** happens conversationally, through a Claude Code skill
(`.claude/skills/add-word/`). I share a word — usually with the sentence it
appeared in — and Claude:
1. Confirms the specific sense of the word from context
2. Writes an English translation
3. Writes a definition *in the target language itself*, not just a
   translation gloss
4. Appends a new entry to `vocab.json`

The language-native definition is a deliberate design choice, not an
afterthought. Producing and reading a definition in the language you're
learning is a stronger comprehension exercise than a translation gloss — it
keeps you thinking in the language rather than just mapping words back to
English.

**Reviewing** happens either in the terminal or in a browser — same review
logic and same `vocab.json` either way, just two interfaces on top of it.

CLI:

```bash
python3 review.py
```

Web UI:

```bash
python3 run_ui.py
```

It shows whatever cards are due today, one at a time, in one of two modes:

- **Write (the default)** — you're shown the English meaning and type the
  target-language word from memory, article included for French nouns
  (e.g. "la cigogne"). Typed answers get checked against the correct form,
  with some leeway for accent typos and missing/wrong articles — those get
  flagged as "close" rather than marked wrong outright.
- **Recognize** — you see the word, recall the meaning yourself, then
  reveal and self-report honestly whether you actually knew it.

Write mode is the default because production (typing a word from memory) is
a meaningfully stronger recall test than recognition — the same reasoning
behind the "no AI during composition" principle elsewhere in the learning
roadmap. Recognize mode is still there for days that call for something
lighter.

**There's no manual Hard/Good/Easy self-rating.** An earlier version asked
for that on every card, the same way Anki does — but in practice it went
mostly unused: you only ever rate a word *after* getting it right, by which
point it rarely feels "hard" even when it genuinely was a struggle to get
there. So difficulty now comes from actual behavior instead of in-the-moment
self-report:

- Missing a word — on the first attempt *or* on a retry — immediately
  triggers a same-screen retype: same prompt, a fresh input, no jump to a
  different card. This happens on the spot, while the word is still fresh.
- If a word gets missed enough times in one session (3+, cumulative across
  first attempt and retries) before you eventually get it right, it's
  auto-flagged **priority** — reviewed more often going forward. This is a
  forward-looking signal only; it never changes the SM-2 outcome that
  already got locked in for that session's actual review.
- You can also flag any card priority manually at any time (the ☆/★ toggle
  in both modes), independent of the auto-flagging.

The real SM-2 rating (the thing that actually schedules the next review
date) is now computed automatically from how the answer checked — exact,
close, or wrong — not from a self-reported scale. Retyping after a miss is
purely for practice; it never submits a second rating for the same word.

## The SM-2 algorithm

Every card tracks three numbers: `repetitions` (how many times in a row
you've remembered it), `easiness` (a multiplier that grows for words you find
easy and shrinks for ones you find hard), and `interval` (days until the next
review). After each review, all three update based on how well you did —
forget a word and it resets to daily review; remember it easily several times
in a row and the interval stretches out, sometimes to weeks or months. Over
time this converges on showing you each word right around the point you're
about to forget it, which is where spaced repetition gets its actual value
over just re-reading a list repeatedly.

The full implementation is in `review.py` — it's short and commented enough
to read end to end if you want to see exactly how it works.

## Data model

Everything lives in `vocab.json`, a flat array of entries:

```json
{
  "id": 1,
  "word": "s'égarer",
  "language": "fr",
  "translation_en": "to lose one's way, to wander off, to stray",
  "definition_in_language": "Se perdre, ne plus savoir où l'on est ou où l'on va.",
  "source_sentence": "Le chat semblait s'égarer dans les couloirs sombres du vieux manoir",
  "source_title": "Le Comte de Monte-Cristo",
  "date_added": "2026-09-07",
  "tags": [],
  "cultural_note": "",
  "gender": null,
  "era": null,
  "srs": {
    "repetitions": 0,
    "easiness": 2.5,
    "interval": 0,
    "next_review": "2026-09-07",
    "last_reviewed": null
  }
}
```

`era` is an optional, controlled-vocabulary tag (`review.py`'s `ERAS`
registry — e.g. `"serfdom_era"`, `"archaic"`) for words genuinely tied to a
specific bygone period, not everyday vocabulary. Purely a visual signal — a
small colored chip in review — and it never touches scheduling. Most
entries leave it `null`.

`gender` is `"m"` or `"f"` for nouns (French has only two), and `null` for
everything else (verbs, adjectives, adverbs). This isn't just metadata —
`review.py` displays nouns with their article (e.g. "la cigogne") rather than
the bare word, so gender gets practiced as part of recalling the word itself,
the same way it actually gets used, instead of being a separate fact to
memorize on the side.

`cultural_note` is populated only when a word carries real cultural or
historical weight — a period-specific term, an idiom with a documented
origin, a word whose meaning is tied to a specific historical institution or
event. Most everyday words leave it empty; it's a bonus, not an obligation on
every entry. When present, it also surfaces during review — a story or
historical hook tends to make a word stick better than a bare definition
alone. Finding further reading (articles, deeper history) is intentionally
*not* automated here — it stays an on-demand ask ("find me an article about
this") rather than a step baked into every word capture, so the core
add-a-word flow stays fast for the common case.

`language` is a short code (`fr`, `ru`, `zh`) — the schema was designed to
support Russian and Mandarin from the start, and Russian is now genuinely
live and in daily use alongside French (both in the many hundreds of
entries, growing from ongoing reading — currently *Отцы и дети* and
*Муму*). Mandarin hasn't started yet; it'll eventually need additional
fields (character, pinyin, tone) that don't apply to alphabetic languages —
that extension stays deferred until the Mandarin-specific project work is
further along, rather than guessed at now.

**Multiple languages in the pool at once:** review sessions (CLI and web UI
both) only ask which language to review when there's actually more than one
due on a given day — which, now that Russian and French are both live, is
the normal case rather than a hypothetical. Articles are French-only too: `display_word()` only ever attaches "le/la/l'"
when an entry's `language` is `"fr"`, so a Russian noun's `gender` (which can
be `"m"`, `"f"`, *or* `"n"` — Russian has three) stays informational rather
than triggering a (wrong) French article.

## Not everything gets added

A lesson from an old Quizlet habit: recording every unknown word regardless
of how useful it actually is to practice leads to spending real review time
on things like the name of a specific tree species that will probably never
come up again. Lexi is built to avoid repeating that.

Two things enforce this:
- **Asking about a word and adding it to the pool are different actions.**
  Asking Claude what something means, in conversation, never touches
  `vocab.json` on its own — only an explicit request to add it does.
- **The add-word skill flags words that look rare, narrowly technical, or
  archaic/dated before adding them**, and asks whether it's actually worth
  active practice or just worth understanding right now. Words added despite
  the flag (common for archaic terms in older texts — worth recognizing, not
  necessarily worth being able to produce) get tagged (`"archaic"`, `"rare"`,
  `"technical"`) rather than blending in indistinguishably with everyday
  vocabulary, so the pool stays legible even as it grows.

## Keeping the prompts honest

A card is only a real recall test if the prompt doesn't accidentally hand
you the answer. Two leak patterns turned up in practice, both now guarded
against in the `add-word` skill before an entry is ever saved:

- **Same-word leaks** — an English translation that restates the target
  word's own root in parentheses (e.g. defining a derived word by
  literally showing the base word it's built from) effectively answers the
  question inside the prompt itself. Caught across a sweep of the existing
  deck and fixed by moving that kind of etymological note into
  `cultural_note` instead, which only displays *after* the answer is
  revealed — the interesting "oh, that's why" context survives, the leak
  doesn't.
- **Loanword leaks** — more specific to Russian than French: if a word's
  correct English gloss is just an English-accented transliteration of the
  word itself (тройка → "troika," тарантас → "tarantas"), writing that
  gloss as the prompt lets you answer by transliterating the English prompt
  back into Cyrillic, without recalling the word from memory at all. The
  fix is the same shape — describe the underlying concept in plain English,
  and save the "this is usually called X in English" fact for
  `cultural_note`.

**Niche words also don't compete evenly with everyday vocabulary from day
one.** Entries tagged `archaic`, `rare`, or `technical` get a 14-day-out
`next_review` instead of today, pushing their first appearance out rather
than flooding review with a chapter's worth of one-off period terms the
moment they're captured. It's a data-only decision — `due_today()` just
checks the date — so it needed no scheduling-logic changes, only a
different starting value.

## Why this design (the pedagogy behind it)

The whole tool is built around retrieval before feedback, not feedback
available throughout. Both the "no AI assistance while reading, only after"
principle in the broader learning roadmap this project belongs to, and the
SM-2 algorithm itself, rest on the same underlying idea from second-language-
acquisition research (related to Bjork's desirable-difficulties research,
and to the "generation effect"): struggling to recall something yourself,
then getting corrected or reinforced, builds a stronger memory trace than
having the answer available the whole time. Lexi doesn't quiz you *while*
you're reading — it captures the word, then makes you actually retrieve it
later, on a schedule designed to hit right before you'd naturally forget it.

**The same principle applies one step earlier than the tool itself covers,
and that's on the reader, not the code.** Reflexively asking for a
definition the moment an unfamiliar word shows up, the same way Lexi's
review mode avoids giving feedback throughout, skips the same productive
struggle Bjork's research is actually about. So the real-world rule I've
settled on: let the word sit and try to infer it from context first, and
only ask when comprehension genuinely requires it or the word seems worth
deliberately practicing — not on reflex. Worth being precise about *which*
difficulties are worth sitting with, though (a distinction the same Bjork
paper is careful to draw): a word that's actually inferable from context,
cognates, or repetition is worth the struggle. A word like чуланчик or
барщина — a specific historical term with no compositional transparency —
isn't; there's nothing to infer, so asking immediately there isn't
skipping a desirable difficulty, it's just getting information that
guessing was never going to produce anyway.

## The web UI

`run_ui.py` starts a small local server (`api.py`, built with FastAPI) and
opens the review interface in your browser. It's a thin wrapper, not a
second implementation — `api.py` imports `review.py` directly and reuses its
SM-2 logic, word display, and answer-checking as-is. The only new code is
the API layer (a handful of endpoints: what's due, check an answer, submit a
rating, toggle priority) and the browser page itself (`web/`) that calls them.

Runs entirely on `127.0.0.1` (your own machine) — nothing is reachable from
the internet, there's no account, and there's nothing to pay for. Stop it
any time with Ctrl+C.

This also fixes something the CLI genuinely couldn't: typing accented
characters. Terminal apps don't support macOS's press-and-hold accent
popup, so getting é/è/ê/ç into a terminal review session meant memorizing
Option-key dead-key combos. A browser text field is a normal Cocoa text
input, so the built-in accent popup just works.

The API/frontend split is also intentional groundwork, not just how FastAPI
happens to work: if this ever becomes a phone-installable app (a PWA), it
would talk to this same API rather than needing its own copy of the review
logic. Nothing about that is built yet — this is browser-only, at your own
desk, for now — but the separation means it wouldn't require a rebuild.

## Image credits

- **Rose** (bottom right) — *Rosa centifolia foliacea*, a hand-colored
  engraving by Pierre-Joseph Redouté from *Les Roses* (1817-1824), via
  [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Redoute_-_Rosa_centifolia_foliacea.jpg).
  Public domain (Redouté died 1840).
- **Butterfly** (top left) — one specimen cropped from Plate 12 of
  *Papillons* (1925) by Émile-Allain Séguy, via
  [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Papillons_(Pl._12)_BHL48852969.jpg)
  (digitized by Smithsonian Libraries via BHL). Public domain (published
  1925, author died 1951).

No attribution legally required for either, but credited here anyway
since it's good practice. Backgrounds removed and images cropped/isolated
locally; original files untouched.

### Vocab-card images

A handful of vocab entries (specific, unfamiliar physical objects where
even the English gloss doesn't paint a clear picture — see IDEAS.md) carry
an optional reveal-only image, shown after answering alongside
cultural_note, never in the prompt itself:

- **шинель** (id 393) — a Russian soldier in a greatcoat, 1862, via
  [New York Public Library Digital Collections](https://commons.wikimedia.org/wiki/File:Russian_soldier_from_1862.JPG),
  from Wikimedia Commons. Public domain (published before 1931).
- **тулуп** (id 408) — Sergey Ivanov, *Peasant in the Sled* (1904-1905),
  via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:S._V._Ivanov._Peasant_in_the_sled._(1904-1905).jpg)
  (Tatarstan State Museum of Fine Arts). Public domain (artist died 1910).
- **сюртук** (id 796) — a man's frock coat, France, c. 1816-1820, via
  [Los Angeles County Museum of Art](https://commons.wikimedia.org/wiki/File:Man%27s_silk_and_wool_twill_frock_coat_c._1820.jpg),
  from Wikimedia Commons. Public domain.
- **картуз** (id 481) — Vasily Vereshchagin, *A Boy in a Black Kartuz*
  (1880-1901), via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Парень_в_черном_картузе.jpg)
  (Kyiv National Art Gallery). Public domain (published before 1931).
- **косынка** (id 544) — Hariton Platonov, *Ukrainian Girl* (1896), via
  [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Платонов_Дівчина-українка_1896.jpg).
  Public domain (artist died 1907).

All five resized locally (longest side capped at 500px) to keep file
sizes reasonable; originals untouched elsewhere. More may be added the
same deliberate, one-at-a-time way described in IDEAS.md — never
auto-generated for every concrete noun.

## Status

v2 — manual definitions via Claude (no API calls from the tool itself), JSON
storage, CLI and browser-based review (Write and Recognize modes, both),
automatic retry-based difficulty signal replacing manual self-rating,
priority flagging (automatic and manual), era tagging, and two generations
of answer-leak fixes baked into the add-word skill. Russian and French are
both genuinely live; Mandarin isn't started yet.

See `IDEAS.md` for design discussion on what's next but not built
(grammar-construction drills as a separate review mode, deeper niche-word
scheduling weight, a review-stats view) and the author's broader
[language + AI learning roadmap](../career-agent/learning_roadmap.md) for
how this fits the bigger picture (auto-fetched definitions, character-aware
scheduling for Mandarin, semantic search across entries, possibly a PWA if
the web UI gets real daily use).
