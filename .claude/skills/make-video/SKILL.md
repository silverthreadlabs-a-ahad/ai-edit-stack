---
name: make-video
description: Edit raw footage into a finished short video hands-off with the AI Edit Stack - analyze clips, pick the best shots, music and SFX, build the HyperFrames composition, review a frame sheet, and render only on request. Use for any "make a video/reel/short from these clips" request in this folder.
---

# make-video

Arguments: `<project-name> [brand] [mode]`. Defaults: brand from the user or `default`, mode `standard`.
Modes (config/stack.json): `quick` (template only, no stop), `standard` (beat-sheet stop, light custom
animation), `premium` (more candidates, full custom animation). Respect each mode's limits.

## 0. Setup (skip what exists)
- No project yet: `.\aes.cmd new <name> --brand <brand> --mode <mode>`.
  Clips go in `inbox/<name>/` (or pass `--source <folder>`). If the folder is empty, ask the user for it.
- Read `projects/<name>/BRIEF.md`. If it is blank, infer goal, length and mood from the footage
  in step 2 and state your assumptions in one line at the end of step 3.

## 1. Analyze (scripts only, 0 tokens)
`.\aes.cmd analyze <name>` -> cached per clip; writes `candidates.md`.

## 2. Describe b-roll (cheap model)
`.\aes.cmd describe <name> --pending` -> `describe_pending.json`.
If it lists any units, spawn the `clip-describer` subagent with the project name. It writes
`describe_out.json` and applies it. Do NOT view the sheets yourself.

## 3. Plan the edit
Read `candidates.md` (only). Then:
1. Story: hook (strongest line or visual) -> problem/value -> proof -> CTA last. Fit the brief's length.
2. Pick units by `q` and flags; use later takes of retakes; skip filler-heavy units or trim them.
3. Music: `.\aes.cmd library suggest --mood "<mood words>" --min-dur <video length+5>` (and `--energy`,
   `--bpm`). Pick one. Start at its `drop` if the hook needs energy, else 0.
   `.\aes.cmd library roles` shows which SFX roles exist (auto SFX skips missing roles).
4. Write `projects/<name>/plan.json` per `docs/PLAN_SCHEMA.md`: shots, transitions (2-3 types max),
   zooms, emphasis words, hook, texts, music, `"sfx": "auto"`.
5. `.\aes.cmd build <name>` -> fix any lint *errors* it prints (warnings are fine).
6. If mode has `beat_sheet_stop`: show the user `beatsheet.md` (paste its table) and wait for an OK or
   changes. In `quick` mode, continue.

## 4. Custom animation (standard: light, premium: full, quick: none)
Only if the brief or brand rules call for graphics beyond captions and kinetic text. Follow
`docs/HYPERFRAMES_GUIDE.md`: registry blocks first, write between CUSTOM markers only, then rebuild.

## 5. Self-review with the frame sheet
`.\aes.cmd framesheet <name>` -> look at `projects/<name>/framesheet.jpg` (one image).
Check it against `docs/REVIEW_CHECKLIST.md`. Fix failures in plan.json (e.g. move a text with `"y"`,
swap a unit, change a transition), rebuild, regenerate the sheet. At most `review_passes` rounds.
For a single frame: `.\aes.cmd framesheet <name> --at 3.2`.

## 6. Hand off
Tell the user, in 3-5 lines: length, shot count, music track (+ credit if CC BY), what you checked, and
the frame sheet path. Offer `.\aes.cmd preview <name>` for live playback. Then STOP.

## 7. Render only on request
- "render" -> `.\aes.cmd render <name>` (pre-cut, voice enhancement, delivery quality, loudness fix,
  export). Takes minutes: run it in the background and report the export path + loudness when done.
- "draft" -> `.\aes.cmd render <name> --draft`.
- Feedback after a render -> edit plan.json, rebuild, framesheet, wait for "render" again.
- Save any lasting preference the user states into the brand's `rules` (brands/<brand>.json) so the
  next video starts with it.

## Budget
Report `.\aes.cmd status <name>` time totals when done. Stop after 2 failed automatic fixes and ask.
