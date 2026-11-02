"""Frame sheet: a labeled storyboard grid of the built composition. No render, seconds to make.

Uses `hyperframes snapshot --at ... --keep` (stills seeked straight from the composition),
then tiles them with time / shot / transition / sfx / caption labels into framesheet.jpg.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .util import fmt_t, info, load_config, npx_hf, project_dir, read_json, step_log


def _font(size: int):
    for f in ("Nirmala.ttc", "Nirmala.ttf", "arialbd.ttf", "arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _pick_times(tl: dict, max_frames: int) -> list[dict]:
    shots = tl["shots"]
    if len(shots) > max_frames - (1 if tl.get("outro") else 0):
        n = max_frames - (1 if tl.get("outro") else 0)
        idx = sorted({round(i * (len(shots) - 1) / max(1, n - 1)) for i in range(n)})
        shots = [shots[i] for i in idx]
    picks = []
    for s in shots:
        dur = s["end"] - s["start"]
        t = s["start"] + min(0.45, dur / 2)
        if s["captions"]:
            t = s["start"] + min(0.6, dur / 2)
        picks.append({"t": round(t, 3), "shot": s})
    if tl.get("outro"):
        picks.append({"t": round(tl["outro"]["start"] + 0.6, 3), "shot": None})
    return picks


def make(name: str, at: str | None = None) -> Path:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    tl = read_json(d / "timeline.json")
    cfg = load_config()
    max_frames = cfg["modes"][pj["mode"]]["framesheet_max_frames"]
    if at:
        picks = [{"t": float(x), "shot": next((s for s in tl["shots"] if s["start"] <= float(x) < s["end"]), None)}
                 for x in at.split(",")]
    else:
        picks = _pick_times(tl, max_frames)
    raw = d / "framesheet_raw"
    with step_log(d, "framesheet", frames=len(picks)):
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir()
        times = ",".join(f"{p['t']:g}" for p in picks)
        res = npx_hf(["snapshot", ".", "--at", times, "--no-end", "--keep", "-o", str(raw)],
                     cwd=d / "hf", check=False)
        files = {}
        for f in raw.glob("at-*.png"):
            m = re.match(r"at-([\d.]+)s\.png", f.name)
            if m:
                files[float(m.group(1))] = f
        if not files:
            err = (res.stderr or b"").decode("utf-8", "replace")[-1500:]
            info(f"snapshot produced no frames.\n{err}")
            raise SystemExit(1)
        sfx = tl.get("sfx", [])
        tiles = []
        first = Image.open(next(iter(files.values())))
        tw = 270 if first.height > first.width else 400
        th = int(tw * first.height / first.width)
        f_big, f_small = _font(15), _font(13)
        for n, p in enumerate(picks):
            f = min(files.items(), key=lambda kv: abs(kv[0] - p["t"]))[1]
            img = Image.open(f).convert("RGB").resize((tw, th))
            tile = Image.new("RGB", (tw, th + 78), (18, 18, 18))
            tile.paste(img, (0, 0))
            dr = ImageDraw.Draw(tile)
            s = p["shot"]
            if s:
                near = [x["role"] for x in sfx if abs(x.get("hit", x["at"]) - s["start"]) < 0.3]
                l1 = f"#{s['n']}  {fmt_t(p['t'])}  {s['unit']}"
                l2 = f"in: {s['transition']}{'  zoom:' + s['zoom'] if s['zoom'] != 'none' else ''}" \
                     f"{'  sfx: ' + ','.join(near) if near else ''}"
                l3 = (" / ".join(s["captions"]) or s.get("desc", ""))[:44]
            else:
                l1, l2, l3 = f"OUTRO  {fmt_t(p['t'])}", "", ""
            dr.text((8, th + 6), l1, font=f_big, fill=(255, 255, 255))
            dr.text((8, th + 30), l2, font=f_small, fill=(255, 196, 0))
            dr.text((8, th + 52), l3, font=f_small, fill=(190, 190, 190))
            tiles.append(tile)
        cols = 4 if tw == 270 else 3
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * (th + 78) + (rows + 1) * 8 + 34), (0, 0, 0))
        ImageDraw.Draw(sheet).text((10, 8), f"{name}  |  {tl['duration']:.1f}s  |  {len(tl['shots'])} shots  |  "
                                             f"brand {pj['brand']}", font=_font(17), fill=(255, 255, 255))
        for i, t in enumerate(tiles):
            r, c = divmod(i, cols)
            sheet.paste(t, (8 + c * (tw + 8), 42 + r * (th + 78 + 8)))
        out = d / "framesheet.jpg"
        sheet.save(out, quality=85)
    info(f"Frame sheet: {out}  ({len(tiles)} frames)")
    return out
