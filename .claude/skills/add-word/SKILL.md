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
   - `definition_in_language` — a definition written *in the target
     language itself* (French, Russian, etc.), not translated from English.
     This is deliberate: reading a definition in the language you're
     learning is a stronger comprehension exercise than a translation gloss,
     and it's a core design choice of this tool, not optional.

3. **Flag uncertainty honestly.** If a word is idiomatic, regional, archaic,
   or otherwise a judgment call, say so plainly rather than presenting a
   guess as settled fact — she can sanity-check it later, but shouldn't have
   to guess which entries need double-checking.

4. **Read the current `vocab.json`**, find the highest existing `id`, and
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
     "srs": {
       "repetitions": 0,
       "easiness": 2.5,
       "interval": 0,
       "next_review": "YYYY-MM-DD (today's date — new cards are due immediately)",
       "last_reviewed": null
     }
   }
   ```

   `language` is a short code: `fr` for French, `ru` for Russian, `zh` for
   Mandarin. Leave `source_sentence` / `source_title` as empty strings if she
   didn't provide them — don't invent a source.

5. **Confirm back to her** in one or two lines: the word, your English
   translation, and the language-native definition — so she can catch an
   error immediately rather than discovering it at review time.

## Example

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
