"""Forced alignment of romanized caption_text to the speech (torchaudio MMS_FA, 1100+ languages,
romanized input), 0 API tokens. Needs the `ml` extra.

aes align <name>   for every plan shot with `caption_text`, finds the exact start/end of each written word
                   in the audio and caches it in cache/<clip>/align.json. `aes build` then uses these
                   times for captions, the word-by-word highlight and `at_word` graphics (falls back to
                   whisper timings when no alignment exists).
"""

from __future__ import annotations

import json
import re
import subprocess

import numpy as np

from .util import info, path_of, project_dir, read_json


def align_key(t0: float, t1: float, text: str) -> str:
    return f"{t0:.2f}-{t1:.2f}|{text}"


def _letters(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


def _audio(src: str, t0: float, dur: float, sr: int = 16000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", src,
                          "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def align(name: str) -> None:
    import torch
    import torchaudio
    from .project import load_units
    d = project_dir(name)
    pj = read_json(d / "project.json")
    plan = read_json(d / "plan.json")
    units = {u["gid"]: u for u in load_units(pj)}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=False).to(dev).eval()
    tokenizer, aligner = bundle.get_tokenizer(), bundle.get_aligner()
    sr = bundle.sample_rate
    n = 0
    for i, s in enumerate(plan.get("shots", [])):
        text = s.get("caption_text")
        u = units.get(s["unit"])
        if not text or not u:
            continue
        t0 = max(0.0, u["t0"] + float(s.get("trim_in", 0)))
        t1 = min(u["probe"]["duration"], u["t1"] - float(s.get("trim_out", 0)))
        words = text.split()
        clean = [_letters(w) for w in words]
        idx = [k for k, c in enumerate(clean) if c]
        pad = 0.15
        a0 = max(0.0, t0 - pad)
        wav = torch.from_numpy(_audio(u["source"], a0, (t1 - a0) + pad, sr))[None].to(dev)
        with torch.inference_mode():
            emission, _ = model(wav)
            spans = aligner(emission[0], tokenizer([clean[k] for k in idx]))
        ratio = wav.size(1) / emission.size(1) / sr
        times = [None] * len(words)
        for k, sp in zip(idx, spans):
            times[k] = (round(a0 + sp[0].start * ratio, 3), round(a0 + sp[-1].end * ratio, 3))
        # words with no letters (numbers, symbols) get the gap between their neighbours
        for k in range(len(words)):
            if times[k] is None:
                prev = times[k - 1][1] if k and times[k - 1] else t0
                nxt = next((times[j][0] for j in range(k + 1, len(words)) if times[j]), t1)
                times[k] = (prev, max(prev, nxt))
        f = path_of("cache") / u["cache"] / "align.json"
        cur = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        cur[align_key(t0, t1, text)] = [[w, a, b] for w, (a, b) in zip(words, times)]
        f.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        n += 1
        info(f"  shot {i + 1} {s['unit']}: aligned {len(words)} words")
    info(f"Aligned {n} shots. Rebuild to use the exact word times: aes build {name}")
