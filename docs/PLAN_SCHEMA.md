# plan.json reference

`projects/<name>/plan.json` is the edit decision list. Claude writes it; `aes build` turns it into the
HyperFrames composition. Every field except `shots` is optional.

```json
{
  "title": "Orders not coming",
  "hook": { "text": "ORDERS NOT COMING?", "dur": 1.5, "y": 420, "sfx": "impact" },
  "shots": [
    { "unit": "c01-u001", "transition": "cut", "emphasis": ["orders"],
      "caption_text": "Collection ready hai aur orders phir bhi nahi aa rahe" },
    { "unit": "c03-u001", "transition": "whip", "trim_out": 1.3, "zoom": "slow" },
    { "unit": "c01-u007", "transition": "zoom", "zoom": "punch", "reframe_x": 0.42 },
    { "unit": "c01-u011", "transition": "cut", "caption": true, "emphasis": ["dm"] }
  ],
  "texts": [ { "at": 6.2, "dur": 1.6, "text": "REAL > PERFECT", "y": 380, "sfx": "swoosh-text" } ],
  "music": { "file": "music/upbeat/upbeat-corporate_soundrider.mp3", "start": 8.96, "volume": 0.38,
             "snap_cuts": true },
  "sfx": "auto",
  "outro": true
}
```

## shots[] (in playback order)
| field | default | meaning |
| --- | --- | --- |
| `unit` | required | id from candidates.md, e.g. `c02-u014` |
| `trim_in` / `trim_out` | 0 | seconds cut from the unit's start / end (negative extends into the source) |
| `transition` | `cut` | how this shot comes in: `cut`, `crossfade` (0.25 s overlap, audio crossfades), `whip` (slide + motion blur, auto whoosh), `zoom` (punch-in from 1.25x, auto impact), `flash` (white flash, auto impact). The first shot is always `cut`. |
| `zoom` | `none` | whole-shot treatment: `punch` (1.12x, hides jump cuts, adds energy), `slow` (1.0 to 1.06 push) |
| `caption` | true | burn word-timed captions for speech units |
| `caption_text` | none | replaces the caption words (romanized Hindi/Urdu, spelling fixes); re-timed over the spoken span |
| `emphasis` | [] | caption words styled with the brand accent (colour, underline or serif) |
| `reframe_x` | face x | horizontal crop centre (0-1) when the source is wider than the canvas |

Captions are placed automatically in the brand's caption spot and moved below or above the face when
the detected face would collide (`y_normal`, `y_low`, `y_top` in the brand).

## hook / texts[]
Big kinetic text (brand `kinetic` style). `at` and `dur` in timeline seconds, `y` = top in px.
`sfx` = a library role (`impact`, `pop`, `swoosh-text`, `riser`, `none`). The hook always starts at 0.

## music
`file` relative to `library/` (from `aes library suggest`). `start` = offset into the track (use its
`drop` for an energetic open). `volume` overrides the brand bed level. The bed is ducked under speech and
lifted in b-roll gaps automatically, and fades out at the end (or before the outro, per brand).
`snap_cuts` moves each cut to the nearest beat within 0.25 s when that does not clip a word.

## sfx
`"auto"`: whoosh on whips, impact on zoom/flash, the text's role on kinetic texts (peaks aligned to the
cut). `"none"`: no SFX. Or an explicit list: `[{"at": 4.1, "role": "pop"}, {"at": 9.0, "file": "sfx/riser/x.mp3", "align": "end"}]`
(`align`: `start` | `peak` | `end` at `at`).

## outro
`true` appends the brand outro (crossfade / last-frame hold per brand). `false` skips it.
