---
name: add-word
description: Add a new vocabulary word to Lexi (Julia's personal spaced-repetition vocab tool) while reading. Triggers when Julia shares a word she just encountered, in any supported language (French, Russian, eventually Mandarin), and wants it captured with a definition.
---

# Add a word to Lexi

Julia is reading in a foreign language and just hit a word she wants to save.
She'll tell you the word, usually with the sentence she found it in and
optionally the book/source title. Your job: explain it clearly, then append a
properly-formatted entry to `vocab.json` in this project.

## What to do

1. **Confirm the word and its context.** If she gave you the sentence it
   appeared in, use that to pin down the specific sense — many words have
   multiple meanings, and the sentence tells you which one actually applies
   here. If she didn't give a sentence, ask for it if you're not confident
   which sense she means; if you are confident, it's fine to proceed and just
   note you inferred it from the word alone.

2. **Write two definitions:**
   - `translation_en` — a natural, concise English translation or gloss.
     **Keep this field free of any French (or other target-language) text**
     — no related words, no etymology, no "from the verb 'X'" asides, even
     when genuinely interesting. `review.py`'s Write mode shows this field
     as the prompt and has Julia type the target-language word from memory,
     so anything here that shares a root with the answer gives it away
     before she's had to recall it. If the etymology is worth knowing, it
     belongs in `cultural_note` instead — never in `translation_en`.
   - `definition_in_language` — a definition written *in the target
     language itself* (French, Russian, etc.), not translated from English.
     This is deliberate: reading a definition in the language you're
     learning is a stronger comprehension exercise than a translation gloss,
     and it's a core design choice of this tool, not optional.

3. **Flag uncertainty honestly.** If a word is idiomatic, regional, archaic,
   or otherwise a judgment call, say so plainly rather than presenting a
   guess as settled fact — she can sanity-check it later, but shouldn't have
   to guess which entries need double-checking.

4. **Before adding, flag low-value words rather than adding automatically.**
   Julia's explicit goal is *not* to repeat a mistake from her old Quizlet
   habit, where every unknown word got recorded regardless of how useful it
   actually was to practice. If a word seems rare, highly technical/narrow
   (e.g. a specific plant or animal species, a niche professional term), or
   archaic/dated and unlikely to come up in modern usage, say so and ask a
   quick one-line question — something like *"This one's pretty rare/dated —
   want it in your active practice pool, or just explained for now?"* — before
   writing it to the file. If she says "just explain it," give the
   explanation in conversation and stop there; don't write anything to
   `vocab.json`. Common, everyday words don't need this check — only flag
   words where frequency or usefulness is genuinely in question.

5. **If she does want a flagged word added anyway** (common for archaic terms
   in older texts she wants to recognize but not necessarily produce), tag it
   in the entry's `tags` array — e.g. `["archaic"]`, `["rare"]`,
   `["technical"]` — so it's marked as different from everyday vocabulary
   rather than blending in indistinguishably. Everyday words get `tags: []`.

5a. **Add a cultural/historical note when a word genuinely has one — not for
    every word.** If a word connects to real cultural or historical context
    (a period-specific term, an idiom with a real historical origin, a word
    whose meaning shifted for a specific historical reason), write 2-3
    sentences about it in `cultural_note`. Most everyday words won't have
    anything interesting to say here — leave it as an empty string rather
    than stretching for a note that isn't genuinely there. This is a bonus,
    not an obligation on every entry. Don't search the web for this — use
    what you already know; if she wants to go deeper on something, she'll
    ask you to find an article, which is a separate, on-demand request, not
    part of this flow.

6. **Read the current `vocab.json`**, find the highest existing `id`, and
   append a new entry with `id` one higher (start at `1` if the file is
   empty). Use this exact shape:

   ```json
   {
     "id": 1,
     "word": "the word or short phrase",
     "language": "fr",
     "translation_en": "...",
     "definition_in_language": "...",
     "source_sentence": "the sentence it appeared in, if given",
     "source_title": "book/article title, if given",
     "date_added": "YYYY-MM-DD (today's date)",
     "tags": [],
     "cultural_note": "",
     "gender": "m or f — omit / use null for verbs, adjectives, adverbs, etc.",
     "srs": {
       "repetitions": 0,
       "easiness": 2.5,
       "interval": 0,
       "next_review": "YYYY-MM-DD (today's date — new cards are due immediately)",
       "last_reviewed": null
     }
   }
   ```

   **For nouns, always set `gender`** (`"m"` or `"f"` — French has only two).
   This isn't optional metadata; review.py displays the word with its article
   (e.g. "la cigogne") so gender gets practiced as part of recalling the word
   itself, not as separate trivia. For non-nouns (verbs, adjectives, adverbs),
   leave `gender` as `null` — there's nothing to track.

   `language` is a short code: `fr` for French, `ru` for Russian, `zh` for
   Mandarin. Leave `source_sentence` / `source_title` as empty strings if she
   didn't provide them — don't invent a source.

5. **Confirm back to her** in one or two lines: the word, your English
   translation, and the language-native definition — plus the cultural note,
   when there is one — so she can catch an error immediately rather than
   discovering it at review time.

## Examples

**A word with no special cultural weight** — most entries look like this:

Julia says: *"Add 's'égarer' — from 'Le chat semblait s'égarer dans les
couloirs sombres du vieux manoir', from Le Comte de Monte-Cristo."*

You would append:

```json
{
  "id": 4,
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
  "srs": {
    "repetitions": 0,
    "easiness": 2.5,
    "interval": 0,
    "next_review": "2026-09-07",
    "last_reviewed": null
  }
}
```

(`gender` is `null` here — "s'égarer" is a verb, not a noun.)

**A word that genuinely does carry cultural/historical weight:**

Julia says: *"Add 'bagne' from the same book."*

```json
{
  "id": 5,
  "word": "bagne",
  "language": "fr",
  "translation_en": "penal colony, forced-labor prison",
  "definition_in_language": "Établissement où étaient détenus et forcés au travail les condamnés aux peines les plus lourdes.",
  "source_sentence": "",
  "source_title": "Le Comte de Monte-Cristo",
  "date_added": "2026-09-07",
  "tags": [],
  "cultural_note": "France operated real penal colonies (bagnes) — most famously at Toulon, Brest, and later French Guiana — where convicts sentenced to \"travaux forcés\" (hard labor) were held, often for life. The word carries the specific historical weight of that system, not just \"prison\" generically — worth keeping in mind since it shows up constantly in 19th-century French literature dealing with crime and punishment.",
  "gender": "m",
  "srs": {
    "repetitions": 0,
    "easiness": 2.5,
    "interval": 0,
    "next_review": "2026-09-07",
    "last_reviewed": null
  }
}
```

Then reply something like: *"Added **s'égarer** — 'to lose one's way, to
wander off, to stray.' In French: 'Se perdre, ne plus savoir où l'on est ou
où l'on va.'"*
