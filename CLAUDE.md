# AI Edit Stack: rules for Claude

You are the editor. Scripts do the seeing, hearing and encoding; you make the decisions.
The full workflow is the `make-video` skill (`.claude/skills/make-video/SKILL.md`). Use it for every edit request.

## Commands (run from this folder)
`.\aes.cmd <cmd>` (PowerShell) or `./aes.cmd <cmd>` (bash). Main ones:
`new`, `analyze`, `describe --pending|--apply`, `library suggest|roles|fetch|index`, `build`,
`framesheet`, `preview`, `render [--draft]`, `status`. `aes doctor` checks the setup.
Local AI (0 tokens): `vision <name>` (SigLIP tags + embeddings for b-roll), `match <name> "phrase" ...`
(ranks shots for each voiceover phrase, Hindi/Urdu/English), `align <name>` (exact word times for
romanized `caption_text`; run after writing plan.json, before `build`).

## Token budget rules (the user cares about time AND tokens)
1. Never open raw video, full transcripts, analysis.json or logs. Read `candidates.md`,
   `beatsheet.md`, `timeline.json` and `framesheet.jpg` only.
2. Never look at contact sheets yourself. Describing clips is the `clip-describer` subagent's job
   (Haiku). Descriptions are cached forever per clip.
3. Do not write a composition from scratch. `aes build` generates it from `plan.json`.
   Use `graphics[]` blocks (badge, arrow_label, highlight_word, phone_reels, gag, cta) before any custom code.
   Custom work goes only in `projects/<name>/custom.{css,html,js}`.
4. Review with the frame sheet (one image), not with many frames or full renders.
5. Fix the failing shot in `plan.json` and rebuild. Never re-plan the whole video for one fix.
6. At most `limits.max_fix_retries` (2) automatic fix rounds; then stop and report to the user.
7. Do not render until the user says "render" (a draft render is allowed only if they ask for one).

## Edit quality rules (apply always, then the brand's `rules`)
- Hook in the first 1.5 s: the strongest line or visual goes first.
- Prefer units with high `q` and no `blurry/dark/shaky/retake->` flags. For a retake, use the later take.
- Drop units with filler words unless they carry meaning; trim with `trim_in/trim_out` instead.
- Use at most 2-3 transition types per video. Most cuts are `cut`. A `whip` or `zoom` needs a reason
  (energy change, new section). `crossfade` is for time passing or the outro.
- Cut on the beat: keep `snap_cuts: true` unless the edit is dialogue-driven and snapping hurts.
- Never put text over a face. Check every caption and kinetic text against the frame sheet.
- The CTA lands last before the outro, even if it was spoken earlier.
- Music: pick with `aes library suggest`, match energy to the brief, start at the drop when the hook is
  strong. Credit CC BY music (CREDITS.txt is generated).
- Hindi/Urdu or misspelled lines: set `caption_text` on the shot (romanized, correctly spelled).

## Automatic roles (from cached analysis, no tokens)
- Voiceover / to-camera lines are detected (8+ clean words, steady pace, face, whisper confidence >= 0.65)
  and listed first in `candidates.md`.
- Clips with no real line (director count-ins like "3, 2, 1, go") become muted b-roll takes.
- B-roll is grouped per clip; only one unit per one-scene clip is described (its description covers the clip).
- Use `cover` on a voiceover shot to lay b-roll over the voice.
- Face tracks (YuNet, 2 fps, cached per clip): captions, kinetic texts and blocks without a `y` are placed
  off faces automatically; anything with a fixed `y` that hits a face prints `LAYOUT:` in the build output.
  Fix every LAYOUT line before review.

## Where things are
- `projects/<name>/`: BRIEF.md, candidates.md, plan.json (you write it), hf/ (HyperFrames project),
  beatsheet.md, timeline.json, framesheet.jpg, renders/, runlog.jsonl
- `brands/*.json`: brand presets (fonts, colours, caption spot, audio levels, outro, rules)
- `docs/PLAN_SCHEMA.md`: every plan.json field. `docs/HYPERFRAMES_GUIDE.md`: custom animation rules.
  `docs/REVIEW_CHECKLIST.md`: what the frame-sheet review checks.
