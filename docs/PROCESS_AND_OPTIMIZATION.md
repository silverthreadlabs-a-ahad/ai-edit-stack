# AI Edit Stack: the full process, alternatives, and how to make it faster and cheaper

Written 2026-11-02 after editing a client product reel (voiceover over a model shoot).
It covers how a reel is made today, what each step costs, the alternative tools for each step, the
recommended choice, and a prioritized list of improvements.

---

## 1. The reel used as the reference case

| Item | Value |
|---|---|
| Source | one SD-card dump of a product shoot: 43 clips, 1080x1920, 50 fps |
| Content | 38 model takes (hoodies on a curtain backdrop, director counting in "3, 2, 1, go") plus 5 presenter voiceover takes (Hindi/Urdu, ~21 s usable) |
| Output | 20.5 s reel + 4.9 s Rava outro = 25.2 s, 9:16, Instagram |
| Shots | 5 presenter segments, 7 b-roll covers over her voice, 3 mini clips in a phone mockup |
| Graphics | 2 coloured kinetic words, ✕ badge, 2 arrow labels, darken+blur gag, phone cut-away, highlight word, masked-rise CTA with red underline |
| Captions | Romanized, word-by-word highlight, accent words in red, Montserrat 800 |
| Music | `library/music/upbeat/awesome.mp3` from its drop (12.54 s) |

---

## 2. The pipeline step by step (what actually happened)

### Step 0: Context
- **Tools:** Read (memory files, `CLAUDE.md`, `make-video` skill, `brands/rava.json`).
- **Purpose:** load the standing Rava rules: no text on faces, white "Rava", masked-rise + red underline ending,
  0.25 s crossfade into the Rava outro, grade preferences, 4K delivery.

### Step 1: Project setup
- **Tool:** `aes new <name> --brand rava --mode standard --source <folder>`
- **Output:** `projects/<name>/BRIEF.md`, `project.json` (clip aliases c01..c43 pointing at the source files).
- **Cost:** seconds, 0 tokens.

### Step 2: Analysis (runs locally, 0 tokens)
- **Tool:** `aes analyze <name>`
- **What it runs per clip:**
  - ffprobe: resolution, fps, duration, audio.
  - PySceneDetect: scene cuts (threshold 27, min 0.8 s).
  - faster-whisper (medium, CUDA): word-level transcript, language detection.
  - OpenCV: sharpness (Laplacian variance), brightness, shake (frame motion), face position/size.
  - Retake detection (text similarity ≥ 0.72), filler words.
  - 3-frame contact sheets per unit.
- **Output:** `candidates.md` (human/AI-readable table) + `candidates.json`; per-clip cache in `cache/<clip>-<hash>/`.
- **Time:** 541 s (9 min) for 43 clips. Cached forever, so a re-run on the same footage is near-instant.
- **Problem found:** the director's count-in ("3, 2, 1, go", "action") made 38 b-roll clips look like
  speech. The stack listed 122 speech units and only 2 b-roll units.

### Step 3: Shot descriptions (cheap model)
- **Tools:** 2 subagents on Haiku, run in parallel. Each made 66 tool calls:
  - 1 Read of its list;
  - 62 Reads of contact-sheet images;
  - 1 Write of the JSON;
  - 1 Bash `aes describe --apply`;
  - 1 hand-back.
- **Output:** one line per shot, e.g. "two men in dark green and pink hoodies walk in profile, medium-wide, static, beige curtain".
- **Cost:** 76,733 + 78,751 ≈ **155k Haiku tokens**, about 70-80 s wall-clock.
- **Note:** the project's `clip-describer` agent was not available because the session started in `E:\`,
  not in `E:\AI-Edit_stack`. A general-purpose agent with model haiku and the same instructions was used instead.

### Step 4: Clip selection and outline (main model)
- **Inputs read:** `candidates.md`, the 124 descriptions, and word timings of the 5 voiceover takes only.
- **Decisions:**
  - Map each voiceover phrase to the best shot.
  - Use the "bad" shots on purpose for the red-flags section.
  - Reject head-cropped, dim and shaky units.
- **Output:** an outline table for user approval (the beat-sheet stop of `standard` mode).

### Step 5: Stack extensions (one-time code changes, now permanent)
- **`aes/build.py`:**
  - `cover` (b-roll over a speech shot, muted);
  - `color` on kinetic texts;
  - exact per-word caption timing when `caption_text` has the same word count as the transcript;
  - `brand` override in `plan.json`;
  - `caption.active_word` (karaoke highlight).
- **`aes/render.py`:** covers are pre-cut too.
- **`templates/composition.html`:** `.cap .w` dim/active word styles.
- **`docs/PLAN_SCHEMA.md`:** documents `cover` and `color`.

### Step 6: plan.json
- 5 shots with word-snapped trims.
- 7 covers.
- Romanized `caption_text` + `emphasis`.
- 2 coloured kinetic texts.
- Zoom transition into the second section.
- Music from its drop, `snap_cuts: false` (the cuts are driven by the dialogue).
- `"sfx": "auto"`, outro on, brand overrides for fonts/captions.

### Step 7: Build
- **Tool:** `aes build <name>`
- **Output:**
  - `hf/index.html` (HyperFrames + GSAP);
  - `timeline.json`, `beatsheet.md`, `CREDITS.txt`;
  - lint result.
- **Time:** 2-6 s per build, 9 builds ≈ 30 s.

### Step 8: Custom graphics
- **Where:** hand-written CSS/HTML/JS between the CUSTOM markers. Kept as `custom.css`, `custom.html` and
  `custom.js` in the project and injected with `splice.py`.
- **ffmpeg:** cut three 0.6 s clips for the phone mockup.
- **Lint issue fixed:** videos nested inside a timed `div` are not allowed, so the phone wrapper is shown/hidden with GSAP instead.

### Step 9: Review
- **Tool:** `aes framesheet <name> [--at t1,t2,...]` (stills rendered in headless Chrome).
- **Rounds:** 8 sheets ≈ 164 s in total.
- **Fixes it caught:**
  - the highlight word overlapping the caption;
  - the arrow label crowding the caption;
  - the CTA wrapping onto 3 lines, then running past the frame edges;
  - wrong label wording.

### Step 10: Preview
- **Tool:** `aes preview <name>` (HyperFrames Studio at `http://localhost:3003`, reloads automatically).

### Step 11: Feedback round
- Fonts → Montserrat (captions, labels, CTA) + Playfair Display italic (kinetic).
- Word-by-word captions, red accent words, soft shadow. Applied as a `brand` override in `plan.json`
  (the Rava brand file is unchanged).

### Step 12: Render (on request only)
- **Tool:** `aes render <name>`
- **Steps:**
  - voice enhancement (RNNoise, EQ, de-esser, compressor, loudnorm);
  - pre-cut every shot/cover;
  - HyperFrames render at portrait-4K, delivery quality;
  - loudness check/fix to −15 LUFS;
  - copy to `exports/` and `E:\rava-edit\final-renders\<name>\`.

---

## 3. Time and token totals for this reel

| Step | Time | Tokens |
|---|---|---|
| Analyze 43 clips | 541 s | 0 |
| Describe 124 units (2 × Haiku) | ~75 s (parallel) | ~155k Haiku |
| Builds (9) | 30 s | 0 |
| Frame sheets (8) | 164 s | ~1.5-2k each to view (main model) |
| Main model (planning, code, graphics, replies) | most of the remaining time | estimate: ~100-120k context per turn (mostly cached), ~15-20k output |
| **Machine time** | **~13.5 min** | |
| **Wall-clock incl. approvals** | **~45 min** | exact session cost: run `/cost` |

**Where the cost went:**
1. Describing 124 units, caused by the count-in problem.
2. Long main-model context: the stack code had to be read and extended once.
3. Several review rounds on custom graphic placement.

---

## 4. Alternatives for every stage, and the recommended choice

### 4.1 Transcription / word timing
| Option | Speed | Quality (Hindi/Urdu) | Cost | Notes |
|---|---|---|---|---|
| **faster-whisper medium (current)** | Fast on GPU | Good; wrong script (Devanagari for Urdu) | Free | Already integrated |
| faster-whisper **large-v3-turbo** | ~same as medium | Better | Free | Memory note: large-v3 ran out of GPU memory; turbo is smaller and worth testing |
| WhisperX (whisper + wav2vec2 forced alignment) | Fast | Same text, **tighter word timings** | Free | Best for karaoke captions and cutting on exact words |
| whisper.cpp | Fast on CPU | Same as Whisper | Free | Not installed here |
| Deepgram / AssemblyAI / ElevenLabs Scribe (cloud) | Very fast | Good, some do Hinglish | Paid per minute | Adds an upload step and an API key |
| **Recommended** | | | | **Keep faster-whisper; transcribe only the voiceover clips with large-v3-turbo; add WhisperX alignment if caption timing needs to be frame-perfect.** |

### 4.2 Scene / unit splitting
| Option | Notes |
|---|---|
| **PySceneDetect ContentDetector (current)** | Fine for single-take product clips |
| TransNetV2 | Neural cut detector, better on fast edits/flashes; overkill for one-take shoots |
| **Recommended** | Keep PySceneDetect. **Fix the unit logic** (see 5.1) instead. |

### 4.3 Quality scoring (blur, dark, shake)
| Option | Notes |
|---|---|
| **OpenCV Laplacian + luma + motion (current)** | Fast; "shaky" fires on model movement on a tripod |
| pyiqa (MUSIQ, NIQE, BRISQUE) | Learned "aesthetic/technical quality" scores, closer to human taste; GPU recommended |
| Optical-flow camera-motion estimate (global motion vs subject motion) | Separates real camera shake from a moving model |
| **Recommended** | Add global-motion shake (background region only), as already described in the Rava memory: phase-correlation on a static region. Optionally add MUSIQ as one extra score column. |

### 4.4 Face detection (keep text off faces)
| Option | Notes |
|---|---|
| **Current OpenCV-based detector** | Works; misses profiles and turned heads |
| MediaPipe Face Detection / Face Landmarker | Fast, robust to profile, gives a full face box per frame |
| InsightFace / RetinaFace | Most accurate, heavier |
| **Recommended** | MediaPipe, sampled at ~2 fps, storing the face box over time. Then the build can place text per frame window, not per shot. This would have avoided most manual layout fixes. |

### 4.5 Shot description (the biggest token cost)
| Option | Tokens | Time | Quality | Notes |
|---|---|---|---|---|
| **Haiku subagent reading 3-frame sheets (current)** | ~1.2k per unit | ~1 s per unit (parallel) | Good | Simple, but scales with unit count |
| One sheet **per clip** instead of per unit | ~1.2k per clip | Same | Good enough for single-take clips | 43 instead of 124 sheets: **~65 % fewer tokens** |
| **Local vision model** (Qwen2.5-VL 3B/7B, Florence-2, Moondream 2) | **0 API tokens** | 1-4 s per image on GPU | Qwen2.5-VL 7B ≈ Haiku for this task | Needs ~8-16 GB VRAM; one-time setup |
| CLIP / SigLIP embeddings | 0 | Very fast | No sentences, but **text→shot matching scores** | Ideal for "match clip to voiceover line" |
| Gemini (video input) | Paid | Fast | Watches whole clips natively | Different provider; an upload of every clip |
| **Recommended** | | | | **Short term:** one sheet per clip + skip clips the analysis already rejects. **Medium term:** local Qwen2.5-VL (or Florence-2 for captions) + SigLIP embeddings, which takes describe tokens to 0. |

### 4.6 Matching the voiceover to the b-roll
| Option | Notes |
|---|---|
| **Main model reads descriptions + transcript (current)** | Best judgement, costs main-model tokens |
| SigLIP text→image similarity per voiceover phrase | Gives a ranked shortlist per phrase automatically |
| **Recommended** | `aes suggest-covers <name>`: rank the top 3 shots per phrase with SigLIP + quality score, written into `candidates.md`. The main model then just picks from a short list. |

### 4.7 Composition / motion graphics
| Option | Pros | Cons |
|---|---|---|
| **HyperFrames + GSAP (current)** | HTML/CSS = unlimited graphics, deterministic, lint, Studio preview, 4K render | Custom graphics are hand-written each time |
| Remotion (React) | Large ecosystem, good docs | Same hand-writing problem; different stack |
| MoviePy / ffmpeg filtergraphs | No browser | Weak for typography/animation |
| DaVinci Resolve (Python API) / Premiere (FCPXML export) | An editor can fine-tune afterwards | Graphics are hard to automate; slower loop |
| CapCut / Canva templates | Quick for simple reels | Not scriptable, not deterministic |
| **Recommended** | **Keep HyperFrames.** Turn this reel's custom graphics into reusable **plan blocks** (see 5.3) so the next reel writes 0 lines of custom CSS/JS. Add an optional **FCPXML export** if a human editor ever needs to take over. |

### 4.8 Voice enhancement
| Option | Notes |
|---|---|
| **RNNoise + EQ + de-esser + compressor + loudnorm (current)** | Proven on Rava reels |
| DeepFilterNet 3 | Better noise removal, local, free |
| Adobe Podcast Enhance / ElevenLabs Voice Isolator | Excellent, cloud, manual or paid |
| **Recommended** | Keep the current chain; try DeepFilterNet in place of `arnndn` on noisy shoots. |

### 4.9 Music
| Option | Notes |
|---|---|
| **Local library + `aes library suggest` (current)** | Fast; the library is small (3 tracks) |
| Openverse / Freesound (CC) | Free; 504 errors seen; Freesound needs `FREESOUND_API_KEY` |
| Licensed libraries (Artlist, Epidemic) | Best quality; manual download into `library/` then `aes library index` |
| AI music (generated per reel) | Unique bed timed to the cuts |
| **Recommended** | Grow `library/` to 20-30 indexed tracks per mood (beats/drops pre-computed). A bigger library means better matches with 0 extra tokens. |

### 4.9b Sound effects (SFX)

**What is used now:**
- **Source:** the local library `library/sfx/`, 7 files:
  - impact: `impact-bass-1`;
  - pop: `pop`;
  - whoosh: `whoosh`, `whoosh-short`, `whoosh-cinematic`;
  - click: `click-soft`, `typing`.
  - Missing roles: riser, swoosh-text, ding.
- **Index:** `aes library index` stores each file's duration and peak time in `library/sfx.json`.
- **Placement:** `"sfx": "auto"` in `aes build`:
  - whoosh on whip transitions;
  - impact on zoom/flash transitions;
  - each kinetic text's own `sfx` role.
  - The sound's peak is aligned to the cut/text, at volume 0.5 (brand `sfx_volume`), as `<audio>` tracks 11-14.
- **This reel:** impact at 0.0 s (hook word), impact at 9.77 s (zoom), pop at 9.8 s (second section title).
  This is a double hit, and the custom graphics are silent.

**Alternatives:**
| Option | Cost | Notes |
|---|---|---|
| Local library (current) | Free | Too small: every reel sounds the same |
| Freesound.org API | Free (CC0/CC BY) | Supported by `aes library fetch`; needs `FREESOUND_API_KEY` |
| Pixabay / Mixkit / Zapsplat | Free | Manual download into `library/sfx/<role>/` |
| Epidemic Sound / Artlist SFX | Subscription | Best quality and consistency |
| ElevenLabs Sound Effects (AI) | Paid per generation | Custom sounds on demand |

**Improvements:**
- 3-5 variants per role (the build already rotates through them), and fill riser/ding/swoosh-text.
- A default SFX role per graphic block (badge = tick, arrow = soft swoosh, phone = swipe, CTA = whoosh + ding, gag = low thud).
- Skip a sound that lands within 0.15 s of another (no double hits).
- Duck the music ~3 dB under each hit.

### 4.10 Rendering
| Option | Notes |
|---|---|
| **HyperFrames local, x264 pre-cuts (current)** | NVENC disabled: driver 592 < 610 |
| Update the NVIDIA driver → NVENC | Pre-cuts several times faster |
| HyperFrames cloud / Lambda / Cloud Run | Parallel, fast 4K; costs money, uploads footage |
| 1080p draft first, 4K only for the final | Already the approved fast path (reel 13) |
| **Recommended** | **Update the NVIDIA driver to 610+**, keep local, keep draft → final. |

### 4.11 Cutting / clipping (how shots are cut)

**What is used now (three stages):**
| Stage | Tool | How |
|---|---|---|
| While editing | **HyperFrames virtual cuts** | No file is cut. Each `<video>` points at the source with `data-media-start` (in-point), `data-duration` and `data-start` (timeline position). Cut points come from whisper word timestamps + `trim_in/trim_out` + `cover` times. A rebuild takes ~3 s. |
| Phone-mockup clips | **ffmpeg** (manual) | `ffmpeg -ss 8.1 -i CLIP.MP4 -t 0.6 -an -c:v libx264 -crf 16 -pix_fmt yuv420p p1.mp4` |
| Render | **ffmpeg via `_precut()` in `aes/render.py`** | Every shot and cover is cut to `hf/assets/clips/<id>.mp4`: x264 CRF 16 (NVENC when the driver allows), the cleaned-up voice track muxed in, and a check that the output has a video stream. HyperFrames then renders from these small files. |

**Alternatives:**
| Option | Speed | Quality | Notes |
|---|---|---|---|
| **ffmpeg + libx264 CRF 16 (current)** | Medium (CPU) | Near-lossless | Frame-accurate; the safe default |
| ffmpeg + **h264_nvenc / hevc_nvenc** | **3-6× faster** | Near-lossless at `-cq 16-18` | Needs NVIDIA driver 610+ (machine has 592). Already coded; it switches on automatically. |
| ffmpeg **stream copy** (`-c copy`) | Instant | Lossless | Cuts only on keyframes (camera GOP ~0.5-1 s), so cut points drift. Not usable for word-accurate cuts. |
| **Smart cut** (re-encode only the partial GOP at each edge, stream-copy the middle): LosslessCut, `smartcut` | Near-instant | Lossless middle | Best of both for long clips; less useful for 1-3 s shots, which are mostly edges anyway |
| ffmpeg to an **intermediate codec** (ProRes 422 / DNxHR HQ, all-intra) | Fast to encode, bigger files | Visually lossless | All-intra files decode much faster during the 4K HyperFrames render (every frame is a keyframe): fewer extraction failures, faster seeking |
| PyAV (Python bindings to ffmpeg) | Same as ffmpeg | Same | Lets the stack cut without spawning processes; more code |
| MoviePy | Slow | OK | Simple API, but too slow for 4K batch cutting |
| **Auto-Editor** | Fast | — | Automatically removes silences/dead air from a voiceover take; a good first pass before word-level trims |
| GPU decode (`-hwaccel cuda`) | Faster decode of 4K/50p sources | Same | Helps when sources are 4K; these are 1080p, so the gain is small |

**For better results:**
- **Exact cut points:** word timings from **WhisperX** (forced alignment) are tighter than plain whisper, so cuts land
  right at the first consonant with no breath or clipped syllables. Add 2-3 frame handles and an 8-15 ms audio
  fade at each cut to avoid clicks.
- **Frame-rate conform:** sources are 50 fps on a 30 fps canvas. Pre-cut with `-r 30` (or `fps=30`) so
  HyperFrames doesn't drop frames unevenly. Or set the canvas to 25/50 fps to match the camera (smoother motion).
- **Upscale at cut time for 4K:** `scale=2160:3840:flags=lanczos` in the pre-cut (the approach used on reels 11-13)
  instead of letting the browser scale 1080p video.
- **Grade at cut time:** apply the shared Rava grade (gamma + mid curve) in the same ffmpeg pass. That's one
  encode instead of two.
- **J/L cuts:** cut the voice and the picture separately (voice as its own `<audio>`, picture muted) so the voice
  can lead or trail a picture cut. The `cover` feature already does this for b-roll.

**Recommended:**
1. Update the NVIDIA driver to use NVENC (biggest free speed-up).
2. Pre-cut to **all-intra** (x264 `-g 1` or ProRes) with conform + lanczos upscale + grade in one pass.
3. WhisperX timings with short audio fades at every cut.
4. Auto-Editor as an optional dead-air pass on long voiceover takes.

---

## 5. Improvements, ranked by impact

### 5.1 Treat count-in speech as b-roll (big token + time saver)
- **Problem:** "3, 2, 1, go / action / ready / okay" made 38 b-roll clips look like speech, so 124 units needed describing.
- **Fix in `aes/analyze.py`:** if a unit's transcript contains only count-in words (numbers in any language,
  "go", "action", "ready", "ok", "yeah", "chalo", "shuru") or fewer than ~4 meaningful words, mark it `kind: broll`.
  Also mark the whole clip as b-roll when the speaker's face is not the subject (no face, or the voice is off-mic: low level, high reverb).
- **Also:** describe **one sheet per b-roll clip** when the clip is a single scene.
- **Expected:** 124 → ~40 descriptions (**~100k fewer Haiku tokens**, ~45 s less).

### 5.2 Find the voiceover takes automatically
- Score clips as "VO candidates": continuous speech > 3 s, face present and steady, mic-level audio,
  little silence. Flag them `VO` in `candidates.md` with a joined romanized-ready script.
- Mark retakes of the same sentence (e.g. a later take repeating the end of an earlier one) and keep the best one.
- **Expected:** removes a reading/thinking pass for the main model.

### 5.3 Turn this reel's graphics into reusable plan blocks (the biggest time saver for future reels)
Add these as `texts[].style` or `graphics[]` types generated by `aes build`, so no hand-written CSS/JS is needed:
| Block | Plan example |
|---|---|
| `badge` (✕ / ✓ circle + label) | `{"type":"badge","icon":"x","text":"Label","at":3.6,"dur":1.86,"y":300}` |
| `arrow_label` | `{"type":"arrow_label","text":"Point at this","from":[330,1595],"to":[420,1505],"at":13.5}` |
| `highlight_word` (word + sweeping bar) | `{"type":"highlight_word","text":"Key point","color":"#2fbf5b","y":320}` |
| `phone_reels` (tilted phone, N clips, progress bars, white cut-away, dark captions) | `{"type":"phone_reels","units":["c16-u006","c28-u003","c33-u001"],"at":11.9,"dur":1.5}` |
| `footage_gag` (darken / blur / B&W on a word) | `{"type":"gag","target":"cover","effects":[["dark",8.62],["blur",9.06]]}` |
| `cta_mask_rise` (Rava ending) | `{"type":"cta","lines":["Your call","to action"],"at":18.72}` |
- Times can be given **as words** instead of seconds: `"at_word": "keyword"`. The build resolves them from the transcript.
- Remove the `splice.py` workaround: the build should read `custom.css/html/js` files from the project folder directly.
- **Expected:** custom-graphics time goes from ~15-20 min to ~2 min per reel; main-model output tokens drop by ~60-70 %.

### 5.4 Face-aware auto layout
- Store face boxes over time (MediaPipe, ~2 fps) for speech and b-roll.
- The build places every caption/graphic in the free zone (above head / mid-chest / bottom safe area),
  checks for overlap between graphics and captions, and auto-shrinks text that would wrap past the safe width.
- **Expected:** most frame-sheet fix rounds disappear (this reel needed 4 placement fixes).

### 5.5 Auto-match covers to the voiceover
- SigLIP embeddings for every b-roll unit (computed once in analyze).
- `aes suggest-covers <name>` lists the top 3 shots per voiceover phrase with quality, so the main model picks from a short list.

### 5.6 Make Rava defaults match what was approved here
If the new look is approved for future reels, move the overrides from `plan.json` into `brands/rava.json`:
- Montserrat captions and `active_word`;
- Playfair Display kinetic;
- `accent_style: color`;
- the soft shadow.

Then every reel starts with them and nothing is re-specified.

### 5.7 Session hygiene (main-model tokens)
- **Start Claude Code in `E:\AI-Edit_stack`**, not `E:\`. The project's `clip-describer` agent and skills then load
  directly, and the context starts smaller.
- **One session per reel.** Long sessions keep re-reading old context. Start fresh for the next reel; the stack,
  memory and brand files carry everything over.
- **Use `quick` mode** for simple talking-head reels (no beat-sheet stop, no custom graphics).
- **Batch frame-sheet times:** one `--at` sheet with all graphic moments per round.

### 5.8 Faster machine time
| Change | Saves |
|---|---|
| NVIDIA driver 610+ → NVENC pre-cuts | Several minutes per 4K render |
| Analyze in parallel (2 clips at a time; GPU whisper + CPU scoring overlap) | ~40 % of the 9 min analyze |
| Transcribe at 16 kHz mono extracted once; skip whisper on clips flagged b-roll by a quick VAD check | Most whisper time on b-roll |
| Low-res proxies (540p) for scoring and frame sheets | Faster sheets, faster preview |
| `--frames-cache-dir E:/hf-cache` (already set) | Keeps C: free |

---

## 6. Projected effect of the improvements (estimates)

| Metric | This reel | After 5.1 + 5.2 | After 5.1-5.5 + 5.8 |
|---|---|---|---|
| Analyze time | 9.0 min | ~6 min (VAD skip) | ~4 min (parallel + skip) |
| Haiku describe tokens | ~155k | ~50k | ~0 (local vision model) |
| Custom-graphics work | ~15-20 min, hand-written | same | ~2 min (plan blocks) |
| Frame-sheet fix rounds | 4 | 4 | 0-1 (auto layout) |
| Main-model output tokens | ~15-20k | ~12k | ~5k |
| Wall-clock to first preview (excluding user approval) | ~35 min | ~25 min | ~10-12 min |

These are estimates; measure with `aes status <name>` (time) and `/cost` (tokens) after each change.

---

## 7. Recommended order of work

1. **Count-in → b-roll + one sheet per clip** (5.1): small code change, biggest token saving.
2. **Reusable graphic blocks + word-anchored timing** (5.3): biggest time saving per reel.
3. **NVIDIA driver update** (5.8): free speed-up for every render.
4. **Promote the approved look into `brands/rava.json`** (5.6), if the client likes it.
5. **MediaPipe face boxes + auto layout** (5.4).
6. **Local vision model + SigLIP matching** (4.5, 5.5): zero describe tokens.
7. **VO auto-detection** (5.2) and **WhisperX alignment** (4.1).

---

## 7b. Implementation status (updated 2026-11-02)

| Improvement | Status | Where |
|---|---|---|
| 5.1 Count-in takes → muted b-roll; b-roll grouped per clip; describe one unit per one-scene clip | **Done**: 124 → ~41 describe units on this shoot | `aes/project.py` (`_assign_roles`, `write_candidates`, `describe_*`) |
| 5.2 Voiceover auto-detection (clean words, pace, face, whisper confidence ≥ 0.65) | **Done**: finds exactly the 5 VO takes here | `aes/project.py` (`_is_vo`) |
| 5.3 Reusable graphic blocks timed by word (`badge`, `arrow_label`, `highlight_word`, `phone_reels`, `gag`, `cta`) | **Done**: this reel now has 0 lines of custom code | `aes/blocks.py`, `aes/build.py`, `docs/PLAN_SCHEMA.md` |
| Custom files read directly (no splice step) | **Done** | `aes/build.py` |
| SFX: default sound per block, short variants for blocks, skip hits within 0.15 s, no track overlaps | **Done** | `aes/build.py`, `aes/blocks.py` |
| Pre-cut: all-intra, fps conform, lanczos upscale to delivery size, 10 ms audio fades | **Done** | `aes/render.py` (`_precut`) |
| Stale `render.html` removed on build (lint error after a render) | **Done** | `aes/build.py` |
| CTA auto-fit to the safe width | **Done** (in the `cta` block) | `aes/blocks.py` |
| 5.4 Face tracks + automatic layout | **Done** with OpenCV **YuNet** instead of MediaPipe (no install, 230 KB model): 2 fps tracks cached per clip; captions/texts/blocks without `y` avoid faces for their whole time on screen; fixed `y` that hits a face prints `LAYOUT:` | `aes/faces.py`, `aes/build.py` |
| 4.5/5.5 Local vision + clip matching | **Done** with **SigLIP multilingual** (a 7B VLM does not fit 6 GB VRAM): `aes vision` tags + embeds all b-roll (119 units in ~4 min first run, cached); `aes match` ranks shots per phrase in Hindi/Urdu/English (~18 s). `describe.engine = "hybrid"`: Haiku only for the top 15 clips | `aes/vision.py`, `config/stack.json` |
| 4.1 Exact word timing | **Done** with **torchaudio MMS forced aligner** instead of WhisperX (aligns the romanized `caption_text` itself): `aes align`, used by captions, word highlight and `at_word` | `aes/align.py`, `aes/build.py` |
| 4.1 large-v3-turbo | **Done**: default model; better Hindi/Urdu text (conf 0.92 vs 0.82). Language pinned per brand (`"language": "hi"` for Rava) because turbo translates to English when it guesses "en" | `config/stack.json`, `brands/rava.json`, `aes/analyze.py` |
| VO detection under turbo | **Done**: whisper confidence no longer separates voiceover from director lines, so a direction-word + repetition score was added (director 0.3-0.7, voiceover 0-0.08, cutoff 0.2) | `aes/project.py` |
| 5.8 Parallel analyze | **Done**: GPU transcribes clip N+1 while the CPU scores clip N (2 workers); face tracks are backfilled for cached clips | `aes/analyze.py` |
| 5.6 Rava default look | **Done**: Montserrat captions with word highlight + red accents, Playfair Display italic kinetic, in `brands/rava.json` | `brands/rava.json` |
| Environment | torch 2.8 cu128, torchaudio, transformers in the `ml` extra; `aes.cmd` keeps HF/torch/uv caches on E: | `pyproject.toml`, `aes.cmd`, `setup/setup.ps1` |
| NVIDIA driver 610+ for NVENC | **Your action** (system install, admin + reboot); the stack switches to NVENC on its own | |

---

## 8. Quick command reference

```powershell
cd E:\AI-Edit_stack
.\aes.cmd new <name> --brand rava --mode standard --source "<folder>"
.\aes.cmd analyze <name>
.\aes.cmd describe <name> --pending      # then the clip-describer agent
.\aes.cmd library suggest --mood "upbeat" --min-dur 30
.\aes.cmd build <name>
.\aes.cmd framesheet <name> --at 0.5,4.3,9.5
.\aes.cmd preview <name>                 # http://localhost:3003
.\aes.cmd render <name> --draft          # 1080p check
.\aes.cmd render <name>                  # final 4K + loudness + export
.\aes.cmd status <name>                  # time per step
```
