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

**Reviewing** happens with `review.py`, a small CLI script:

```bash
python3 review.py
```

It shows whatever cards are due today, one at a time. You rate how well you
remembered each one (Again / Hard / Good / Easy), and the script schedules
the next review date using SM-2.

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
  "srs": {
    "repetitions": 0,
    "easiness": 2.5,
    "interval": 0,
    "next_review": "2026-09-07",
    "last_reviewed": null
  }
}
```

`language` is a short code (`fr`, `ru`, `zh`) — the schema is designed to
support Russian and Mandarin from the start, even though French is the first
language actually populated. Mandarin entries will eventually need additional
fields (character, pinyin, tone) that don't apply to alphabetic languages —
that extension is intentionally deferred until the Mandarin-specific project
work is further along, rather than guessed at now.

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

## Status

v1 — manual definitions via Claude (no API calls from the tool itself), JSON
storage, CLI review. See the author's broader
[language + AI learning roadmap](../career-agent/learning_roadmap.md) for
what's next (auto-fetched definitions, character-aware scheduling for
Mandarin, semantic search across entries).
