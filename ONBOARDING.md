# Onboarding: AI Edit Stack

From zero to your first AI-edited video in about 20 minutes. Do steps 1-4 once.

## 1. Install (one time, ~10 min)
Needs Windows 10/11, FFmpeg, Node.js 22+, and Claude Code. An NVIDIA GPU makes transcription
about 10x faster but is optional.

```powershell
powershell -ExecutionPolicy Bypass -File E:\AI-Edit_stack\setup\setup.ps1
```

This installs uv (if missing), a Python 3.12 environment with all packages, the CUDA libraries for
Whisper, warms the HyperFrames CLI, creates the render cache `E:\hf-cache`, downloads the Whisper
models (~2 GB), and runs the doctor.

Check any time:
```powershell
cd E:\AI-Edit_stack
.\aes.cmd doctor
```
Required items must say `[OK]`. Optional ones:
- **NVENC**: needs NVIDIA driver 610+ for FFmpeg 9. Until you update, pre-cuts use x264 (works, slower).
- **CUDA for Whisper**: without it, Whisper runs on CPU with the `small` model.

## 2. Pick or create your brand (one time per brand)
Ready: `brands/latent.json`, `brands/rava.json` (built from your saved preferences), `brands/default.json`.

For a new brand, copy `default.json` to `brands/<brand>.json` and set:
- `fonts_css` (a Google Fonts URL), `colors`, `caption` (font, size, the caption spot `y_normal`,
  `y_low` when the speaker sits low, `y_top` above the head)
- `audio` levels and `target_lufs`
- `outro.file` (or `null`), `exports_dir`
- `rules`: plain sentences Claude must follow. Add to them whenever you correct an edit.

## 3. Build the music and SFX library (one time, then top up)
The library is what makes music and sound choices good and cheap, so curate it.

Already seeded from your Latent projects: 3 music tracks, 7 SFX (whoosh, pop, impact, click).
Add more:
```powershell
.\aes.cmd library fetch music "upbeat corporate" --mood upbeat -n 5
.\aes.cmd library fetch music "chill lofi" --mood chill -n 5
.\aes.cmd library fetch music "cinematic epic" --mood cinematic -n 5
.\aes.cmd library fetch sfx "whoosh transition" --role whoosh -n 4
.\aes.cmd library fetch sfx "riser" --role riser -n 3
.\aes.cmd library fetch sfx "text swoosh" --role swoosh-text -n 3
.\aes.cmd library fetch sfx "notification ding" --role ding -n 2
.\aes.cmd library roles
```
- Sources: Openverse (no key; CC0 + CC BY only). If Openverse is down (it returns 504 at busy times),
  get a free key at https://freesound.org/apiv2/apply, run `setx FREESOUND_API_KEY <key>`, reopen the
  terminal and add `--provider freesound`.
- Your own files: drop them into `library/music/<mood>/` or `library/sfx/<role>/`, then run
  `.\aes.cmd library index`. Add a same-name `.json` with `{"license": "by", "attribution": "..."}`
  when credit is required.
- Listen to fetched tracks once and delete the bad ones; then run `library index` again.
- CC BY tracks need credit: every build writes `CREDITS.txt`; paste it into the post caption.

## 4. Open Claude Code in the stack folder
```powershell
cd E:\AI-Edit_stack
claude
```
Claude reads `CLAUDE.md` (rules and token budget) and has the `make-video` skill and the
`clip-describer` agent from `.claude/`.

## 5. Your first video
1. Put raw clips in `E:\AI-Edit_stack\inbox\<project-name>\` (any mix of talking head and b-roll).
2. In Claude Code, say for example:
   > /make-video spring-drop latent standard. 30-40s reel, confident and upbeat, CTA "DM us SPRING".
3. Claude creates the project, analyzes, describes b-roll, plans, builds, and (in standard mode) shows
   you the **beat sheet**, a table of every shot, caption, transition and SFX. Reply "ok" or give changes.
4. Claude reviews the **frame sheet** (`projects/<name>/framesheet.jpg`) itself, fixes problems, and
   hands it to you. Open the image to see the whole video at a glance.
   Want to see motion and hear audio? `.\aes.cmd preview <name>` opens live playback, no render.
5. Give feedback with timestamps ("2.4s: swap that shot", "hook text lower"). Claude edits the
   plan and shows a new frame sheet in seconds.
6. Say **"render"**. You get `exports/<name>/<name>.mp4` (plus your brand export folder) with
   voice enhancement and loudness at the brand target.

Optional: fill `projects/<name>/BRIEF.md` before step 2 for tighter results (goal, length, hook, CTA,
mood, must-include and must-avoid).

## 6. Everyday workflow
| You want | Say or run |
| --- | --- |
| A routine post, fastest | `/make-video <name> <brand> quick` |
| A normal reel | `/make-video <name> <brand>` (standard) |
| A launch piece | `/make-video <name> <brand> premium` |
| A rough watch-through | "draft render" (fast, lower quality) |
| Time spent | `.\aes.cmd status <name>` |
| The same footage, another cut | `aes new <name2> --source inbox\<name>`: analysis is reused from the cache |

Token use: in Claude Code, `/cost` (API) or `/context` shows usage. The stack keeps it low by giving
Claude text summaries and one frame-sheet image instead of footage.

## 7. Teaching it your taste
Each correction you give once should never be needed again:
- Lasting style rules → Claude adds them to `rules` in `brands/<brand>.json`.
- Levels, caption spot, fonts → the brand's `audio` / `caption` fields.
- Defaults such as candidate counts, review rounds and Whisper model → `config/stack.json`.

## 8. Troubleshooting
| Problem | Fix |
| --- | --- |
| `analyze` is slow / "whisper on cuda failed" | `.\aes.cmd doctor`; without CUDA it runs on CPU (`model_cpu`) |
| Captions show boxes for Hindi/Urdu | the brand font lacks the script: Claude sets `caption_text` (romanized) |
| Text over a face | tell Claude the time; it moves the text (`y`) or changes the shot |
| Render fails on frame extraction | it retries with `--low-memory-mode` automatically; render one 4K job at a time |
| C: drive fills during renders | the frame cache is on `E:\hf-cache` (config `paths.hf_frames_cache`) |
| Openverse 504 / timeouts | retry later or `--provider freesound` |
| Music too quiet/loud under voice | change `audio.music_volume` in the brand (0.38 ≈ 8 dB under voice) |
| Start over on a clip | `.\aes.cmd analyze <name> --force` |

## 9. Example project
`projects/test-run/` is a worked example built while setting up the stack (your Latent and Rava test
footage, Latent brand). It has a plan.json, beat sheet, frame sheet and a render, so you can see each
file. Delete it any time: `projects\test-run`, `inbox\test-run`, `exports\test-run`.
