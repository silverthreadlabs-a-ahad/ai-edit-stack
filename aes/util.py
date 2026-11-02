"""Shared helpers: paths, config, subprocess, ffprobe, hashing, run log."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi", ".mts"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


# ---------------------------------------------------------------- config

def load_config() -> dict:
    return read_json(ROOT / "config" / "stack.json")


def path_of(key: str) -> Path:
    p = Path(load_config()["paths"][key])
    return p if p.is_absolute() else ROOT / p


def load_brand(name: str) -> dict:
    f = path_of("brands") / f"{name}.json"
    if not f.exists():
        die(f"Brand '{name}' not found at {f}. Available: "
            + ", ".join(p.stem for p in path_of("brands").glob("*.json")))
    return read_json(f)


def project_dir(name: str) -> Path:
    d = path_of("projects") / name
    if not d.exists():
        die(f"Project '{name}' not found. Create it with: aes new {name}")
    return d


# ---------------------------------------------------------------- io

def read_json(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(p: Path, data, compact: bool = False) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- processes

def run(cmd: list[str], check: bool = True, capture: bool = True, cwd: Path | None = None,
        stdin_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=stdin_bytes,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and res.returncode != 0:
        err = (res.stderr or b"").decode("utf-8", "replace")[-2000:]
        die(f"Command failed ({res.returncode}): {' '.join(map(str, cmd))[:400]}\n{err}")
    return res


def npx_hf(args: list[str], cwd: Path | None = None, check: bool = True, capture: bool = True):
    """Run the pinned HyperFrames CLI through npx."""
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    pkg = load_config()["hyperframes"]["npx_package"]
    return run([npx, "--yes", pkg] + args, check=check, capture=capture, cwd=cwd)


def ffprobe(path: Path) -> dict:
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", str(path)])
    data = json.loads(res.stdout.decode("utf-8", "replace"))
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(data.get("format", {}).get("duration") or 0)
    out = {"duration": dur, "has_audio": a is not None, "has_video": v is not None}
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        rot = int(v.get("tags", {}).get("rotate", rot) or rot)
        if abs(rot) % 180 == 90:
            w, h = h, w
        fr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
        try:
            n, d = fr.split("/")
            fps = float(n) / float(d) if float(d) else 30.0
        except Exception:
            fps = 30.0
        out.update({"width": w, "height": h, "fps": round(fps, 3), "codec": v.get("codec_name")})
    return out


def file_key(path: Path) -> str:
    """Stable cache key: name + size + mtime + hash of the first MiB."""
    st = path.stat()
    h = hashlib.sha1(f"{path.name}|{st.st_size}|{st.st_mtime_ns}".encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:10]


def link_or_copy(src: Path, dst: Path) -> None:
    """Hardlink when on the same volume (instant, no extra disk), else copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.stat().st_size == src.stat().st_size:
            return
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def slug(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in s)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:60] or "item"


def fmt_t(t: float) -> str:
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:04.1f}"


# ---------------------------------------------------------------- run log

@contextmanager
def step_log(project: Path | None, step: str, **extra):
    """Time a pipeline step and append it to <project>/runlog.jsonl."""
    t0 = time.time()
    yield
    sec = round(time.time() - t0, 1)
    info(f"[{step}] done in {sec}s")
    if project is not None:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "seconds": sec}
        rec.update(extra)
        with open(project / "runlog.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
