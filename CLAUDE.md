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
- `image`, `image_credit`, `image_in_prompt`: only on request, for hard-to-picture objects. Images come from Wikimedia Commons, public domain or CC BY / CC BY-SA only. They're 500px max, saved as `web/assets/vocab/<transliteration>_<id>.jpg`, with `image_in_prompt: true` and a README credit. The credit shows in the prompt, so it must not name the word or its English clue: describe what's shown ("a man wearing this kind of coat"), then the artist, "via Wikimedia Commons" and the license. In the Ask Claude panel, the `search_commons` and `add_vocab_image` tools (images.py) do all of this.

## Mandarin words

Mandarin is separate from French and Russian. Words live in `mandarin.json` (logic in `mandarin.py`), not `vocab.json`. Julia is learning through Duolingo and sends words as she meets them. The same steps apply: duplicate check (search `mandarin.json` for the characters), explain, propose, add on her yes.

Each word is a triangle: characters, sound and meaning. Lexi practices all six directions as separate schedules, one direction per word per day, with 3 new words a day. Audio comes from the Mac's Mandarin voice in the browser, so there are no files to add.

```json
{
  "id": <max existing id in mandarin.json + 1, starting at 1>,
  "hanzi": "谢谢",
  "pinyin": "xièxie",
  "meaning": "thank you",
  "note": "Optional: shown after she answers (tone notes, the characters' parts, related words)",
  "source": "Duolingo",
  "date_added": "YYYY-MM-DD"
}
```

- Simplified characters. Pinyin with tone marks, syllables written the way dictionaries do (xièxie with its neutral second syllable, nǐ hǎo with a space). Lexi accepts either tone marks or tone numbers when she types.
- `meaning` is shown as a prompt for the meaning → characters and meaning → pinyin directions, so it must not give away the answer. Keep it to the English meaning. Put pinyin, characters or a literal breakdown in `note`.
- Don't add an `edges` or `introduced_on` field. Lexi creates those when she first practices the word.

## Fixing a card

When Julia says a clue is "leaky," it gives away the answer. Rewrite `translation_en` (or the definition) so it doesn't. Move any useful information it held into `cultural_note`, unless the note already covers it.

## Russian spelling

ё counts as е when Lexi checks answers. Still write ё in `word` where it belongs (мотылёк).

## Don't

- Don't commit or push unless she asks.
- Don't reformat `vocab.json` or touch entries she didn't ask about.
