# AI Edit Stack

Hands-off short-form video editing with Claude Code + HyperFrames. Drop raw clips in a folder and
ask Claude for a video. It picks the shots, music, sound effects and transitions, builds the HyperFrames
composition, checks a frame sheet, and renders **only when you say "render"**.

New here? Read **[ONBOARDING.md](ONBOARDING.md)**.

## How it works

```
inbox/<project>/ (raw clips)
  │
  ├─1 ANALYZE ───── PySceneDetect · faster-whisper (GPU) · OpenCV quality + face · contact strips
  │                  cached per clip in cache/  → candidates.md (one line per phrase / b-roll chunk)
  ├─2 DESCRIBE ──── clip-describer subagent (Haiku) writes 1 line per b-roll unit, cached forever
  ├─3 PLAN ──────── Claude reads candidates.md + BRIEF.md → plan.json (shots, music, transitions, text)
  │                  music chosen from library/music.json (BPM, beats, energy, drop, license)
  ├─4 BUILD ─────── aes build → HyperFrames composition: beat-snapped cuts, face-aware captions,
  │                  transitions, auto SFX, ducked music, brand outro  (seconds, nothing encoded)
  ├─5 FRAME SHEET ─ hyperframes snapshot → labelled storyboard grid  (≈20 s, no render)
  │                  Claude self-reviews against docs/REVIEW_CHECKLIST.md, fixes, max 2 rounds
  │                                ↓  you look at one image (or `aes preview` for live playback)
  └─6 RENDER ────── only on request: voice enhancement → pre-cut shots → HyperFrames render
                     → loudness fix to brand target → exports/<project>/ (+ brand export folder)
```

Measured on this machine (RTX 4050, 3 clips / 28 s of footage → 21 s reel): analyze 11 s,
build 2-6 s, frame sheet 19 s, final render 59 s (pre-cut + render + loudness).

## Commands
Run from `E:\AI-Edit_stack` as `.\aes.cmd <command>` (or use the full path from anywhere).

| Command | What it does |
| --- | --- |
| `doctor` | checks every dependency |
| `new <name> --brand latent --mode standard [--source <folder>]` | creates `projects/<name>/` with a BRIEF.md |
| `analyze <name> [--force]` | analyzes clips (cached), writes candidates.md |
| `describe <name> --pending` / `--apply <json>` | b-roll descriptions for the subagent |
| `library fetch music "<query>" --mood <m> -n 5` | downloads CC0/CC BY music (Openverse; `--provider freesound` needs a key) |
| `library fetch sfx "<query>" --role whoosh -n 3` | downloads SFX into a role folder |
| `library index` | tags new library files (BPM, beats, energy, drop, SFX peak) |
| `library suggest --mood upbeat --min-dur 40 [--energy high] [--bpm 100-128]` | top matches, one line each |
| `library roles` | SFX available per role |
| `build <name>` | plan.json → `hf/index.html`, timeline.json, beatsheet.md, CREDITS.txt |
| `framesheet <name> [--at 1.2,4.5]` | storyboard grid `framesheet.jpg` |
| `preview <name>` | HyperFrames Studio in the browser (live, no render) |
| `render <name> [--draft] [--no-precut]` | renders, fixes loudness, exports |
| `status <name>` | progress checklist + time spent per step |
| `cache-clean [--yes]` | drops cache entries for deleted source files |

## Folders
| Folder | Contents |
| --- | --- |
| `aes/` | the Python pipeline |
| `brands/` | brand presets: `latent.json`, `rava.json`, `default.json` |
| `config/stack.json` | modes (quick/standard/premium), Whisper, thresholds, limits |
| `templates/` | composition template, BRIEF template |
| `library/` | `music/<mood>/`, `sfx/<role>/`, `outros/`, generated indexes |
| `inbox/` | raw clips, one folder per project |
| `cache/` | per-clip analysis (reused across projects) |
| `projects/` | one folder per video |
| `exports/` | finished videos + credits |
| `tools/` | RNNoise voice models |
| `docs/` | plan schema, HyperFrames guide, review checklist |
| `.claude/` | the `make-video` skill and the `clip-describer` agent |

## Modes (time vs tokens vs quality)
| Mode | B-roll candidates | Beat-sheet stop | Review rounds | Custom animation | Use for |
| --- | --- | --- | --- | --- | --- |
| quick | 15 | no | 1 | none | routine posts |
| standard | 25 | yes | 2 | light (≤ 2 graphics) | most videos |
| premium | 40 | yes | 2 | full | launches |

Edit limits in `config/stack.json`.
