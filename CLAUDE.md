# Lexi: working notes for Claude

Lexi is Julia's spaced-repetition vocab app for words she meets while reading in French and Russian. All cards live in `vocab.json`. This file is loaded both in her terminal sessions and in the Ask Claude panel built into Lexi (`chat.py`).

## Adding a word

Julia sends a word, a phrase or a whole sentence from her reading.

1. **Check for duplicates first, every time.** Search `vocab.json` for the word, its stem, and other spellings (кастелянша and кастельянша turned out to be the same word). Report what you found.
2. **Explain the meaning** in context, briefly. Point out a more useful phrase or idiom if one is in the sentence.
3. **Propose the card** (clue, definition, note) and **wait for her yes** before adding it. Yes, да, oui and "add it" all count.
4. Add it with a short `python3` script, then read the entry back to confirm.

### Entry format

```json
{
  "id": <max existing id + 1>,
  "word": "...",
  "language": "fr" | "ru",
  "translation_en": "English clue (shown in the Write-mode prompt)",
  "definition_in_language": "Definition in French/Russian (also shown in the prompt)",
  "definition_in_prompt": true,
  "source_sentence": "the sentence she sent, if any",
  "source_title": "",
  "date_added": "YYYY-MM-DD",
  "tags": [],
  "cultural_note": "Shown only after she answers: etymology, usage, related words",
  "gender": "m" | "f" | "n" | null,
  "era": null,
  "srs": {"repetitions": 0, "easiness": 2.5, "interval": 0, "next_review": "<today>", "last_reviewed": null, "first_reviewed_on": null}
}
```

- Load with `json.load`, append, and write back with `json.dump(v, f, ensure_ascii=False, indent=2)`. That matches the file's existing format, so the diff stays small.
- Never change other entries' `srs` data. Julia's review progress is in there.
- French nouns: put the article in `word` (`le`/`la`/`l'`); Lexi checks it.

### Leak check (required)

`translation_en` and `definition_in_language` both appear in the prompt, so neither may give away the answer. Neither may contain:
- the headword or its stem, in any form (the reflexive form, another case, the aspect partner)
- an identical or near-identical English cognate ("requisition" for réquisition)
- a set phrase or nickname that contains the word

Put those in `cultural_note` instead, since it only shows after she answers. Check this with a script before saving, not just by eye. Example: for размолвка, assert that neither `размол` nor `молв` appears in the clue or the definition.

### Russian verbs: two-aspect cards

For a common verb with a common aspect partner, add `"aspect_pair": {"imperfective": "...", "perfective": "..."}` and set `word` to the imperfective form. Lexi then asks for both forms on one card. Fixed phrases can use it too (взвешивать / взвесить последствия). Skip it when the partner is rare. Leak-check both forms.

### Other optional fields

- `variants`: a list of real alternate wordings of the same idiom (e.g. faire le dos rond / faire le gros dos). Only when Julia asks for it.
- `image`, `image_credit`, `image_in_prompt`: only on request, for hard-to-picture objects. Adding an image needs the terminal session (download, resize, README credit).

## Fixing a card

When Julia says a clue is "leaky," it gives away the answer. Rewrite `translation_en` (or the definition) so it doesn't. Move any useful information it held into `cultural_note`, unless the note already covers it.

## Russian spelling

ё counts as е when Lexi checks answers. Still write ё in `word` where it belongs (мотылёк).

## Don't

- Don't commit or push unless she asks.
- Don't reformat `vocab.json` or touch entries she didn't ask about.
