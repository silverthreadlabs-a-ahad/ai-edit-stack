"""Render on request.

  draft  : renders the composition as-is (sources referenced in place), -q draft. Fast check.
  final  : 1) enhance the voice once per source (cached, RNNoise chain from your Rava/Latent work)
           2) pre-cut every used shot to its own short clip (big sources overload frame extraction)
           3) render render.html at delivery quality (+ brand resolution, e.g. portrait-4k)
           4) measure loudness; fix to the brand target with two-pass loudnorm (video copied)
           5) export + credits
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .util import (ROOT, die, ffprobe, info, load_brand, load_config, npx_hf, path_of, project_dir,
                   read_json, run, step_log)

VOICE_CHAIN = ("highpass=f=85,arnndn=m=sh.rnnn:mix=0.9,afftdn=nr=8:nf=-42,"
               "equalizer=f=220:t=q:w=1.1:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=2.5,highshelf=f=9000:g=2,"
               "deesser=i=0.35,acompressor=threshold=-24dB:ratio=3:attack=6:release=90:makeup=2,"
               "loudnorm=I=-14:TP=-1.5:LRA=7,atrim=start=0.0349,asetpts=PTS-STARTPTS")


def _nvenc_ok() -> bool:
    res = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                          "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    return res.returncode == 0


def enhanced_voice(src: Path, cache_name: str) -> Path | None:
    out = path_of("cache") / cache_name / "voice.wav"
    if out.exists():
        return out
    tools = ROOT / "tools"
    if not (tools / "sh.rnnn").exists():
        info("  tools/sh.rnnn missing: voice enhancement skipped")
        return None
    info(f"  enhancing voice: {src.name}")
    res = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-af", VOICE_CHAIN,
                          "-ar", "48000", "-ac", "2", str(out)], cwd=str(tools), capture_output=True)
    if res.returncode != 0:
        info(f"  voice enhancement failed, using original audio: {res.stderr.decode()[-300:]}")
        return None
    return out


def _precut(job: dict, nvenc: bool, crf: int) -> str:
    vcodec = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
              if nvenc else ["-c:v", "libx264", "-preset", "fast", "-crf", str(crf)])
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{job['t0']:.3f}", "-i", job["src"]]
    if job.get("voice"):
        cmd += ["-ss", f"{job['t0']:.3f}", "-i", job["voice"], "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    cmd += ["-t", f"{job['dur'] + 0.05:.3f}"] + vcodec + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                                                          "-movflags", "+faststart", job["out"]]
    run(cmd)
    pr = ffprobe(Path(job["out"]))
    if not pr.get("has_video"):
        die(f"Pre-cut produced no video stream: {job['out']}")
    return job["out"]


def _loudness(path: Path) -> tuple[float, float]:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True)
    txt = res.stderr.decode("utf-8", "replace")
    summ = txt[txt.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summ)
    p = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ)
    return (float(i.group(1)) if i else 0.0, float(p.group(1)) if p else 0.0)


def _fix_loudness(path: Path, target: float, tp: float) -> Path:
    import json
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                          f"loudnorm=I={target}:TP={tp}:LRA=9:print_format=json", "-f", "null", "-"],
                         capture_output=True)
    txt = res.stderr.decode("utf-8", "replace")
    m = json.loads(txt[txt.rfind("{"):txt.rfind("}") + 1])
    out = path.with_name(path.stem + "_lufs.mp4")
    af = (f"loudnorm=I={target}:TP={tp}:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-c:v", "copy", "-af", af, "-ar", "48000",
         "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out)])
    out.replace(path)
    return path


def render(name: str, quality: str = "final", precut: bool = True) -> Path:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    brand = load_brand(pj["brand"])
    cfg = load_config()
    tl = read_json(d / "timeline.json")
    hf = d / "hf"
    renders = d / "renders"
    renders.mkdir(exist_ok=True)
    v = len(list(renders.glob(f"{name}_v*.mp4"))) + 1
    out = renders / f"{name}_v{v}{'_draft' if quality == 'draft' else ''}.mp4"
    frames_cache = cfg["paths"].get("hf_frames_cache")
    if frames_cache:
        Path(frames_cache).mkdir(parents=True, exist_ok=True)

    entry = "index.html"
    if quality == "final" and precut:
        with step_log(d, "precut", shots=len(tl["shots"])):
            units = {c["alias"]: c for c in pj["clips"]}
            nvenc = cfg["render"].get("use_nvenc", True) and _nvenc_ok()
            jobs = []
            for s in tl["shots"]:
                alias = s["unit"].split("-")[0]
                c = units[alias]
                voice = None
                if brand["audio"].get("voice_enhance"):
                    vp = enhanced_voice(Path(c["source"]), c["cache"])
                    voice = str(vp) if vp else None
                jobs.append({"id": s["id"], "src": c["source"], "voice": voice, "t0": s["src"][0],
                             "dur": s["end"] - s["start"], "out": str(hf / "assets" / "clips" / f"{s['id']}.mp4")})
            (hf / "assets" / "clips").mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=cfg["limits"]["parallel_encodes"]) as ex:
                list(ex.map(lambda j: _precut(j, nvenc, cfg["render"]["precut_crf"]), jobs))
            html = (hf / "index.html").read_text(encoding="utf-8")
            for j in jobs:
                html = re.sub(rf'(<video id="{j["id"]}" src=")[^"]+(".*?data-media-start=")[\d.]+(")',
                              rf'\g<1>assets/clips/{j["id"]}.mp4\g<2>0\g<3>', html, count=1)
            (hf / "render.html").write_text(html, encoding="utf-8")
            entry = "render.html"
            info(f"  pre-cut {len(jobs)} clips ({'NVENC' if nvenc else 'x264'})")

    args = ["render", ".", "-o", str(out), "-q", "draft" if quality == "draft" else cfg["render"]["default_quality"]]
    if entry != "index.html":
        args += ["-c", entry]
    if frames_cache:
        args += ["--frames-cache-dir", frames_cache]
    if quality == "final" and brand.get("render_resolution"):
        args += ["--resolution", brand["render_resolution"]]
    with step_log(d, f"render-{quality}", duration=tl["duration"]):
        info(f"Rendering {out.name} ...")
        res = npx_hf(args, cwd=hf, check=False, capture=False)
        if res.returncode != 0 or not out.exists():
            info("Render failed. Retrying once with --low-memory-mode (slower, more robust).")
            res = npx_hf(args + ["--low-memory-mode"], cwd=hf, check=False, capture=False)
            if res.returncode != 0 or not out.exists():
                die("Render failed twice. See output above; try `aes render <name> --draft` to isolate.")

    if quality == "final":
        with step_log(d, "loudness"):
            target, tp = brand["audio"]["target_lufs"], brand["audio"].get("true_peak", -1.5)
            i, p = _loudness(out)
            info(f"  loudness: {i:.1f} LUFS, peak {p:.1f} dBFS (target {target})")
            if abs(i - target) > 1.0 or p > tp + 0.5:
                _fix_loudness(out, target, tp)
                i, p = _loudness(out)
                info(f"  fixed:    {i:.1f} LUFS, peak {p:.1f} dBFS")
        exp = path_of("exports") / name
        exp.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, exp / f"{name}.mp4")
        if (d / "CREDITS.txt").exists():
            shutil.copy2(d / "CREDITS.txt", exp / "CREDITS.txt")
        if brand.get("exports_dir"):
            bd = Path(brand["exports_dir"]) / name
            bd.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, bd / f"{name}.mp4")
            info(f"  exported: {bd / (name + '.mp4')}")
        info(f"  exported: {exp / (name + '.mp4')}")
    info(f"Done: {out}  ({time.strftime('%H:%M:%S')})")
    return out
