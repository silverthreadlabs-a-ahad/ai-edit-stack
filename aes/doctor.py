"""Check that every part of the stack is installed and working."""

from __future__ import annotations

import shutil
import subprocess
import sys

from .util import ROOT, load_config, path_of, read_json


def _ok(flag: bool, label: str, hint: str = "") -> bool:
    print(f"  [{'OK' if flag else '!!'}] {label}" + ("" if flag else f"  -> {hint}"))
    return flag


def doctor(gpu_test: bool = True) -> None:
    good = True
    print("AI Edit Stack doctor")
    good &= _ok(sys.version_info[:2] in ((3, 11), (3, 12)), f"Python {sys.version.split()[0]} (venv)",
                "run setup\\setup.ps1 (creates a Python 3.12 venv)")
    for tool in ("ffmpeg", "ffprobe"):
        good &= _ok(shutil.which(tool) is not None, tool, "winget install Gyan.FFmpeg")
    good &= _ok(shutil.which("node") is not None, "node", "install Node.js 22+")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx:
        pkg = load_config()["hyperframes"]["npx_package"]
        r = subprocess.run([npx, "--yes", pkg, "--version"], capture_output=True)
        good &= _ok(r.returncode == 0, f"HyperFrames CLI ({r.stdout.decode().strip() or pkg})",
                    "check network / npm")
    for mod in ("faster_whisper", "scenedetect", "cv2", "librosa", "PIL", "requests"):
        try:
            __import__(mod)
            _ok(True, f"python: {mod}")
        except Exception as e:
            good &= _ok(False, f"python: {mod}", f"uv sync ({e})")
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                        "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    _ok(r.returncode == 0, "NVENC encoder (fast pre-cuts)", "optional: update the NVIDIA driver to 610+ for FFmpeg 9 NVENC; until then x264 is used")
    if gpu_test:
        try:
            from .analyze import _cuda_dll_setup
            _cuda_dll_setup()
            import ctranslate2
            n = ctranslate2.get_cuda_device_count()
            _ok(n > 0, f"CUDA devices for Whisper: {n}", "optional: Whisper falls back to CPU (slower)")
        except Exception as e:
            _ok(False, "CUDA for Whisper", f"optional ({e})")
    _ok((ROOT / "tools" / "sh.rnnn").exists(), "RNNoise model tools/sh.rnnn (voice enhancement)",
        "copy sh.rnnn into tools/ or set voice_enhance=false in the brand")
    lib = path_of("library")
    mj, sj = lib / "music.json", lib / "sfx.json"
    nm = len(read_json(mj)) if mj.exists() else 0
    ns = len(read_json(sj)) if sj.exists() else 0
    _ok(nm >= 5, f"music library: {nm} tracks", "aes library fetch music \"upbeat corporate\" --mood upbeat -n 5")
    _ok(ns >= 6, f"sfx library: {ns} sounds", "see ONBOARDING.md step 4 (fetch sfx per role)")
    for b in sorted(path_of("brands").glob("*.json")):
        br = read_json(b)
        o = br.get("outro")
        if o:
            from pathlib import Path
            _ok(Path(o["file"]).exists(), f"brand {b.stem}: outro file", f"missing {o['file']}")
    fc = load_config()["paths"].get("hf_frames_cache")
    if fc:
        _ok(True, f"render frame cache: {fc}")
    print("All required checks passed." if good else "Some required checks failed (see -> hints).")
