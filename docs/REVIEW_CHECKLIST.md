# Frame-sheet review checklist

Claude checks `framesheet.jpg` against this list before handing off. Each failure gets a fix in
`plan.json` (or the CUSTOM block), a rebuild, and a new sheet. At most 2 rounds, then report.

| # | Check | Typical fix |
| --- | --- | --- |
| 1 | Frame 1 is a strong visual and the hook text is readable | reorder shots; shorten the hook; change `hook.y` |
| 2 | No caption or kinetic text over any face | `"y"` on the text; `caption: false` for that shot; different unit |
| 3 | No text cut off at the frame edges | shorter text; smaller `max_words` in the brand |
| 4 | No blurry, dark or badly framed shot | swap the unit for one with higher `q` |
| 5 | Transitions: at most 2-3 types, each with a reason | set most to `cut` |
| 6 | Story order: hook -> value -> proof -> CTA last before the outro | reorder `shots` |
| 7 | Captions spelled correctly (names, brand words, romanized lines) | `caption_text` on the shot |
| 8 | Emphasis on 1 word per shot at most | trim `emphasis` |
| 9 | Brand rules from `brands/<brand>.json` all hold | per rule |
| 10 | Length within the brief (see the sheet header) | trim units / drop the weakest shot |

The sheet cannot show motion smoothness or audio. Those are checked by the render step (loudness) and
by the user in `aes preview`.
