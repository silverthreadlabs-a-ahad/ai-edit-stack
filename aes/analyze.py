"""Analyze raw clips once and cache the result.

For every source video this produces, under cache/<stem>-<key>/:
  analysis.json    probe, scenes, and selectable UNITS (speech phrases or b-roll chunks),
                   each with quality scores, face position and flags
  transcript.json  word-level transcript (faster-whisper)
  sheets/<unit>.jpg  3-frame contact strip per unit (cheap for a vision model to read)

A unit is the smallest thing the editor (Claude) picks: one spoken phrase, or one
b-roll chunk of at most `max_broll_unit_sec`. Nothing here costs model tokens.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import ANALYSIS_VERSION
from .util import (VIDEO_EXT, die, ffprobe, file_key, info, load_config, path_of, read_json,
                   write_json)

# ---------------------------------------------------------------- CUDA DLLs (Windows)


def _cuda_dll_setup() -> None:
    """Expose pip-installed NVIDIA runtime DLLs (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
    for site in list(sys.path):
        nv = Path(site) / "nvidia"
        if not nv.is_dir():
            continue
        for sub in nv.iterdir():
            for b in (sub / "bin", sub / "lib"):
                if b.is_dir():
                    try:
                        os.add_dll_directory(str(b))
                    except (AttributeError, OSError):
                        pass
                    os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")


# ---------------------------------------------------------------- media helpers


def decode_audio(path: Path, sr: int = 16000) -> np.ndarray:
    """Decode audio to mono float32 with ffmpeg (avoids PyAV quirks)."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def grab_frame(path: Path, t: float, height: int, aspect: float) -> np.ndarray | None:
    """One BGR frame at time t, scaled to the given height (fast input seek)."""
    w = max(2, int(round(height * aspect / 2)) * 2)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={w}:{height}", "-f", "rawvideo",
         "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    need = w * height * 3
    if proc.returncode != 0 or len(proc.stdout) < need:
        return None
    return np.frombuffer(proc.stdout[:need], dtype=np.uint8).reshape(height, w, 3)


# ---------------------------------------------------------------- transcription


class Transcriber:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None
        self.device = None

    def _load(self, device: str):
        from faster_whisper import WhisperModel
        wc = self.cfg["whisper"]
        if device == "cuda":
            _cuda_dll_setup()
            self.model = WhisperModel(wc["model"], device="cuda", compute_type=wc["compute_type_gpu"])
        else:
            name = wc.get("model_cpu") or wc["model"]
            self.model = WhisperModel(name, device="cpu", compute_type=wc["compute_type_cpu"])
        self.device = device

    def _run(self, audio: np.ndarray):
        wc = self.cfg["whisper"]
        segs, inf = self.model.transcribe(
            audio, language=wc.get("language"), beam_size=wc.get("beam_size", 5),
            word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300})
        words, segments = [], []
        for s in segs:
            i0 = len(words)
            for w in s.words or []:
                words.append([w.word.strip(), round(w.start, 3), round(w.end, 3),
                              round(w.probability, 3)])
            if len(words) > i0:
                segments.append({"s": round(s.start, 3), "e": round(s.end, 3), "w0": i0,
                                 "w1": len(words), "text": s.text.strip()})
        return {"language": inf.language, "words": words, "segments": segments}

    def transcribe(self, audio: np.ndarray) -> dict:
        if audio.size < 1600:
            return {"language": None, "words": [], "segments": []}
        want = self.cfg["whisper"].get("device", "auto")
        order = ["cuda", "cpu"] if want in ("auto", "cuda") else ["cpu"]
        if self.device:
            order = [self.device] + [d for d in order if d != self.device]
        last = None
        for dev in order:
            try:
                if self.model is None or self.device != dev:
                    self._load(dev)
                out = self._run(audio)
                out["device"] = dev
                return out
            except Exception as e:  # missing CUDA libs, OOM, ...
                last = e
                info(f"  whisper on {dev} failed ({type(e).__name__}: {str(e)[:120]}); trying next device")
                self.model = None
        die(f"Transcription failed on all devices: {last}")


# ---------------------------------------------------------------- scenes


def detect_scenes(path: Path, duration: float, fps: float, cfg: dict) -> list[list[float]]:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector
    sc = cfg["scenes"]
    try:
        video = open_video(str(path))
        sm = SceneManager()
        sm.auto_downscale = True
        sm.add_detector(ContentDetector(threshold=sc["threshold"],
                                        min_scene_len=max(1, int(sc["min_scene_sec"] * fps))))
        sm.detect_scenes(video, frame_skip=sc.get("frame_skip", 0), show_progress=False)
        scenes = [[round(s.get_seconds(), 3), round(e.get_seconds(), 3)] for s, e in sm.get_scene_list()]
    except Exception as e:
        info(f"  scene detection failed ({e}); treating clip as one scene")
        scenes = []
    return scenes or [[0.0, round(duration, 3)]]


# ---------------------------------------------------------------- units


def build_units(scenes, tr, duration, cfg) -> list[dict]:
    words = tr["words"]
    seg_bounds = [(s["w0"], s["w1"]) for s in tr["segments"]]
    max_b = cfg["scenes"]["max_broll_unit_sec"]
    units = []

    def add(kind, t0, t1, wi=None):
        if t1 - t0 < 0.5:
            return
        u = {"id": f"u{len(units) + 1:03d}", "kind": kind, "t0": round(t0, 3), "t1": round(t1, 3),
             "dur": round(t1 - t0, 3)}
        if wi:
            u["w"] = list(wi)
            u["text"] = " ".join(words[i][0] for i in range(wi[0], wi[1])).strip()
        units.append(u)

    for s0, s1 in scenes:
        idx = [i for i, w in enumerate(words) if w[1] >= s0 - 0.05 and w[2] <= s1 + 0.05]
        if not idx:
            n = max(1, math.ceil((s1 - s0) / max_b))
            step = (s1 - s0) / n
            for k in range(n):
                add("broll", s0 + k * step, s0 + (k + 1) * step)
            continue
        # phrases: whisper segment boundaries, plus any pause > 0.7 s
        groups, cur = [], [idx[0]]
        seg_starts = {a for a, _ in seg_bounds}
        for i in idx[1:]:
            gap = words[i][1] - words[cur[-1]][2]
            if i in seg_starts or gap > 0.7:
                groups.append(cur)
                cur = [i]
            else:
                cur.append(i)
        groups.append(cur)
        for g in groups:
            t0 = max(s0, words[g[0]][1] - 0.08)
            t1 = min(s1, words[g[-1]][2] + 0.15)
            add("speech", t0, t1, (g[0], g[-1] + 1))
    return units


def _sharp_score(var: float) -> int:
    return int(max(0, min(100, (math.log10(1 + var) - 1) / 1.6 * 100)))


def _expo_score(b: float) -> int:
    if 85 <= b <= 175:
        return 100
    d = 85 - b if b < 85 else b - 175
    return int(max(0, 100 - d * 1.6))


def score_unit(path: Path, u: dict, aspect: float, sheet_dir: Path, face_cascade, cfg) -> None:
    import cv2
    from PIL import Image, ImageDraw
    q = cfg["quality"]
    t0, t1 = u["t0"], u["t1"]
    times = [t0 + 0.15 * u["dur"], (t0 + t1) / 2, t1 - 0.15 * u["dur"]]
    mid = grab_frame(path, times[1], 480, aspect)
    nxt = grab_frame(path, times[1] + 0.2, 240, aspect)
    thumbs = [grab_frame(path, times[0], 240, aspect), None, grab_frame(path, times[2], 240, aspect)]
    if mid is None:
        u["flags"] = ["unreadable"]
        u["q"] = 0
        return
    gray = cv2.cvtColor(mid, cv2.COLOR_BGR2GRAY)
    sharp = _sharp_score(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
    bright = float(gray.mean())
    small = cv2.resize(gray, (nxt.shape[1], nxt.shape[0])) if nxt is not None else None
    motion = 0
    if small is not None:
        motion = int(min(100, float(np.abs(small.astype(np.int16) -
                                           cv2.cvtColor(nxt, cv2.COLOR_BGR2GRAY).astype(np.int16)).mean()) * 4))
    face = None
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                          minSize=(int(gray.shape[0] * 0.06),) * 2)
    if len(faces):
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        H, W = gray.shape
        face = {"cx": round((x + w / 2) / W, 3), "cy": round((y + h / 2) / H, 3),
                "top": round(y / H, 3), "bottom": round((y + h) / H, 3), "h": round(h / H, 3)}
    expo = _expo_score(bright)
    if u["kind"] == "speech":
        qual = 0.5 * sharp + 0.25 * expo + 0.15 * (100 - motion) + (10 if face else 0)
    else:
        qual = 0.65 * sharp + 0.35 * expo
    flags = []
    if sharp < q["sharp_min"]:
        flags.append("blurry")
    if bright < q["bright_min"]:
        flags.append("dark")
    if bright > q["bright_max"]:
        flags.append("blown")
    if u["kind"] == "speech" and motion > 60:
        flags.append("shaky")
    if u["kind"] == "speech" and not face:
        flags.append("no-face")
    u.update({"sharp": sharp, "bright": int(bright), "motion": motion, "q": int(qual),
              "face": face, "flags": flags})
    # contact strip
    thumbs[1] = cv2.resize(mid, (thumbs[0].shape[1], 240)) if thumbs[0] is not None else \
        cv2.resize(mid, (max(2, int(240 * aspect)), 240))
    thumbs = [t if t is not None else np.zeros_like(thumbs[1]) for t in thumbs]
    strip = np.concatenate(thumbs, axis=1)
    img = Image.fromarray(cv2.cvtColor(strip, cv2.COLOR_BGR2RGB))
    canvas = Image.new("RGB", (img.width, img.height + 22), (20, 20, 20))
    canvas.paste(img, (0, 22))
    ImageDraw.Draw(canvas).text((6, 4), f"{u['id']}  {t0:.1f}-{t1:.1f}s  {u['kind']}",
                                fill=(255, 255, 255))
    sheet_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(sheet_dir / f"{u['id']}.jpg", quality=80)


# ---------------------------------------------------------------- driver


def cache_dir_for(src: Path) -> Path:
    return path_of("cache") / f"{src.stem[:40]}-{file_key(src)}"


def _prepare(src: Path, cfg: dict, transcriber: Transcriber, force: bool = False):
    """Stage 1 (GPU, one clip at a time): cache check, probe, transcript. Returns None when cached."""
    cdir = cache_dir_for(src)
    afile = cdir / "analysis.json"
    if afile.exists() and not force:
        a = read_json(afile)
        if a.get("version") == ANALYSIS_VERSION:
            info(f"  cached: {src.name}")
            return None
    info(f"  analyzing: {src.name}")
    pr = ffprobe(src)
    if not pr.get("has_video"):
        info(f"  skipped (no video stream): {src.name}")
        return None
    cdir.mkdir(parents=True, exist_ok=True)
    tfile = cdir / "transcript.json"
    if tfile.exists() and not force:
        tr = read_json(tfile)
    else:
        tr = transcriber.transcribe(decode_audio(src)) if pr["has_audio"] else             {"language": None, "words": [], "segments": []}
        write_json(tfile, tr, compact=True)
    info(f"    {src.name}: transcript {len(tr['words'])} words ({tr.get('device', '-')})")
    return src, cdir, pr, tr


def _finish(src: Path, cdir: Path, pr: dict, tr: dict, cfg: dict) -> Path:
    """Stage 2 (CPU): scenes, units, quality scores, contact sheets, face track."""
    import cv2
    from .faces import face_track
    aspect = pr["width"] / pr["height"]
    scenes = detect_scenes(src, pr["duration"], pr.get("fps", 30), cfg)
    units = build_units(scenes, tr, pr["duration"], cfg)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda u: score_unit(src, u, aspect, cdir / "sheets", cascade, cfg), units))
    face_track(src, cdir, pr["duration"], pr["width"], pr["height"])
    info(f"    {src.name}: {len(scenes)} scenes, {len(units)} units "
         f"({sum(u['kind'] == 'speech' for u in units)} speech)")
    write_json(cdir / "analysis.json", {"version": ANALYSIS_VERSION, "source": str(src.resolve()),
                                        "name": src.name, "probe": pr, "language": tr.get("language"),
                                        "scenes": scenes, "units": units})
    return cdir


def analyze_file(src: Path, cfg: dict, transcriber: Transcriber, force: bool = False) -> Path:
    prep = _prepare(src, cfg, transcriber, force)
    return _finish(*prep, cfg) if prep else cache_dir_for(src)


def list_sources(folder: Path) -> list[Path]:
    if folder.is_file():
        return [folder]
    if not folder.exists():
        die(f"Source folder not found: {folder}")
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    if not files:
        die(f"No video files in {folder}")
    return files


def analyze_sources(sources: list[Path], force: bool = False, language: str | None = None) -> list[Path]:
    """Pipelined: the GPU transcribes clip N+1 while the CPU scores clip N (2 scoring workers)."""
    from .faces import face_track
    cfg = load_config()
    if language:  # pin the language: large-v3-turbo translates to English when it guesses "en"
        cfg["whisper"]["language"] = language
    tr = Transcriber(cfg)
    out: list = [None] * len(sources)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {}
        for i, s in enumerate(sources):
            prep = _prepare(s, cfg, tr, force)
            if prep:
                futs[i] = pool.submit(_finish, *prep, cfg)
            else:
                cdir = cache_dir_for(s)
                out[i] = cdir
                if (cdir / "analysis.json").exists() and not (cdir / "faces.json").exists():
                    a = read_json(cdir / "analysis.json")
                    futs[i] = pool.submit(lambda s=s, c=cdir, p=a["probe"]:
                                          (face_track(s, c, p["duration"], p["width"], p["height"]), c)[1])
        for i, f in futs.items():
            out[i] = f.result()
    return out
