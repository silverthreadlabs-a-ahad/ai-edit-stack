"""Music + SFX library: fetch (Openverse, CC0/CC BY), tag once (BPM, beats, energy, drop, SFX peak),
and suggest matches as a few compact lines, so choosing audio costs almost no tokens.

Layout:
  library/music/<mood>/<track>.mp3  (+ <track>.json sidecar with license/attribution)
  library/sfx/<role>/<sound>.mp3    roles: whoosh pop riser impact click swoosh-text ding
  library/music.json, library/sfx.json   generated indexes
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import requests

from .analyze import decode_audio
from .util import AUDIO_EXT, die, info, path_of, read_json, slug, write_json

OPENVERSE = "https://api.openverse.org/v1/audio/"
UA = {"User-Agent": "ai-edit-stack/1.0 (personal video editing)"}
SFX_ROLES = ["whoosh", "pop", "riser", "impact", "click", "swoosh-text", "ding"]


# ---------------------------------------------------------------- fetch


def _get(url: str, params: dict | None = None, timeout: int = 90, tries: int = 3):
    """GET with retries: Openverse often answers 5xx or times out under load."""
    import time
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code < 500:
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)[:120]
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"request failed after {tries} tries: {last}")


def _search(params: dict) -> list:
    try:
        r = _get(OPENVERSE, params)
    except RuntimeError as e:
        die(f"Openverse unavailable ({e}). Try again later, use --provider freesound "
            "(needs FREESOUND_API_KEY), or drop files into library/ by hand.")
    if r.status_code != 200:
        die(f"Openverse returned {r.status_code}: {r.text[:200]}")
    return r.json().get("results", [])


def _freesound_results(query: str, kind: str, n: int, licenses: str) -> list:
    """Freesound API v2 (free key: https://freesound.org/apiv2/apply). Mapped to Openverse-like dicts."""
    import os
    key = os.environ.get("FREESOUND_API_KEY")
    if not key:
        die("Set FREESOUND_API_KEY (free at https://freesound.org/apiv2/apply) or use --provider openverse")
    lic = []
    if "cc0" in licenses:
        lic.append('"Creative Commons 0"')
    if "by" in licenses.split(","):
        lic.append('"Attribution"')
    dur = "[25 TO 360]" if kind == "music" else "[0.1 TO 8]"
    flt = f"duration:{dur} license:({' OR '.join(lic)})"
    r = _get("https://freesound.org/apiv2/search/text/",
             {"query": query, "filter": flt, "page_size": min(50, n * 4), "token": key,
              "fields": "id,name,username,license,previews,duration,url,tags"})
    if r.status_code != 200:
        die(f"Freesound returned {r.status_code}: {r.text[:200]}")
    out = []
    for s in r.json().get("results", []):
        is_cc0 = "zero" in s.get("license", "").lower()
        out.append({"title": s["name"], "creator": s["username"], "duration": s["duration"] * 1000,
                    "url": s["previews"]["preview-hq-mp3"], "filetype": "mp3",
                    "license": "cc0" if is_cc0 else "by", "license_version": "", "license_url": s["license"],
                    "foreign_landing_url": s["url"], "source": "freesound",
                    "attribution": None if is_cc0 else f"\"{s['name']}\" by {s['username']} ({s['url']}) is licensed under CC BY.",
                    "tags": [{"name": t} for t in s.get("tags", [])]})
    return out


def fetch(kind: str, query: str, n: int, mood: str | None, role: str | None,
          licenses: str = "cc0,by", provider: str = "openverse") -> None:
    lib = path_of("library")
    if kind == "music":
        folder = lib / "music" / slug(mood or query)
        params = {"q": query, "license": licenses, "category": "music", "page_size": min(50, n * 4)}
    else:
        r = role or query.split()[0]
        if r not in SFX_ROLES:
            die(f"SFX role must be one of {SFX_ROLES}")
        folder = lib / "sfx" / r
        # Freesound items carry no Openverse category, so filter by source instead
        params = {"q": query, "license": licenses, "source": "freesound",
                  "page_size": min(50, n * 4)}
    if provider == "freesound":
        results = _freesound_results(query, kind, n, licenses)
    else:
        results = _search(params)
        if not results and "category" in params:
            params.pop("category")
            results = _search(params)
    got = 0
    folder.mkdir(parents=True, exist_ok=True)
    for item in results:
        if got >= n:
            break
        dur = (item.get("duration") or 0) / 1000
        if kind == "music" and not (25 <= dur <= 360):
            continue
        if kind == "sfx" and not (0.1 <= dur <= 8):
            continue
        url = item.get("url")
        ext = "." + (item.get("filetype") or "mp3").lower()
        if not url or ext not in AUDIO_EXT:
            continue
        name = slug(f"{item.get('title', 'track')}-{item.get('creator', '')}")[:50]
        dst = folder / f"{name}{ext}"
        if dst.exists():
            continue
        try:
            data = _get(url, timeout=120)
            data.raise_for_status()
        except Exception as e:
            info(f"  skip {name}: {e}")
            continue
        dst.write_bytes(data.content)
        write_json(dst.with_suffix(".json"), {
            "title": item.get("title"), "creator": item.get("creator"),
            "license": f"{item.get('license')} {item.get('license_version') or ''}".strip(),
            "license_url": item.get("license_url"), "landing": item.get("foreign_landing_url"),
            "attribution": item.get("attribution"), "source": item.get("source"),
            "tags": [t.get("name") for t in item.get("tags") or []][:12]})
        got += 1
        info(f"  + {dst.relative_to(lib)} ({dur:.1f}s, {item.get('license')})")
    info(f"Fetched {got} file(s) into {folder}")
    if got:
        index()


# ---------------------------------------------------------------- tagging


def _music_tags(path: Path) -> dict:
    import librosa
    sr = 22050
    y = decode_audio(path, sr=sr)
    if y.size < sr:
        return {}
    dur = y.size / sr
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    rms = librosa.feature.rms(y=y)[0]
    t = librosa.times_like(rms, sr=sr)
    bins = np.array_split(rms, 8)
    energy = [float(b.mean()) for b in bins]
    peak = max(energy) or 1.0
    energy = [round(e / peak, 2) for e in energy]
    # "drop": biggest 2-second energy rise
    win = max(1, int(2.0 / (t[1] - t[0]))) if len(t) > 1 else 1
    sm = np.convolve(rms, np.ones(win) / win, mode="same")
    rise = sm[win:] - sm[:-win] if len(sm) > win else np.zeros(1)
    skip = int(np.searchsorted(t, 4.0))  # ignore the intro fade-in
    drop = float(t[skip + int(np.argmax(rise[skip:])) + win]) if rise.size > skip + 1 else 0.0
    avg = float(np.mean(energy))
    return {"duration": round(dur, 2), "bpm": round(tempo, 1),
            "beats": [round(float(b), 3) for b in beats], "energy": energy,
            "energy_level": "high" if avg > 0.7 else ("mid" if avg > 0.45 else "low"),
            "drop": round(drop, 2)}


def _sfx_tags(path: Path) -> dict:
    sr = 22050
    y = decode_audio(path, sr=sr)
    if y.size == 0:
        return {}
    env = np.abs(y)
    return {"duration": round(y.size / sr, 3), "peak": round(float(np.argmax(env)) / sr, 3)}


def index(force: bool = False) -> None:
    lib = path_of("library")
    for kind in ("music", "sfx"):
        idx_file = lib / f"{kind}.json"
        old = {e["file"]: e for e in (read_json(idx_file) if idx_file.exists() else [])}
        entries = []
        for f in sorted((lib / kind).rglob("*")):
            if f.suffix.lower() not in AUDIO_EXT:
                continue
            rel = f.relative_to(lib).as_posix()
            st = f.stat()
            prev = old.get(rel)
            if prev and not force and prev.get("mtime") == st.st_mtime_ns:
                entries.append(prev)
                continue
            tags = _music_tags(f) if kind == "music" else _sfx_tags(f)
            if not tags:
                info(f"  unreadable: {rel}")
                continue
            side = f.with_suffix(".json")
            meta = read_json(side) if side.exists() else {}
            group = f.relative_to(lib / kind).parts[0] if len(f.relative_to(lib / kind).parts) > 1 else "misc"
            e = {"file": rel, "mtime": st.st_mtime_ns, "title": meta.get("title") or f.stem,
                 ("mood" if kind == "music" else "role"): group,
                 "license": meta.get("license", "own/unknown"), "attribution": meta.get("attribution"),
                 "tags": meta.get("tags", [])}
            e.update(tags)
            entries.append(e)
            info(f"  tagged {rel}")
        write_json(idx_file, entries)
        info(f"{kind}.json: {len(entries)} entries")


# ---------------------------------------------------------------- suggest


def suggest_music(mood: str | None, min_dur: float, energy: str | None, bpm: str | None,
                  top: int = 6) -> None:
    f = path_of("library") / "music.json"
    if not f.exists():
        die("No music index. Add tracks to library/music/<mood>/ and run: aes library index")
    items = read_json(f)
    lo, hi = (0, 999)
    if bpm:
        a, b = bpm.split("-") if "-" in bpm else (bpm, bpm)
        lo, hi = float(a) - 3, float(b) + 3
    scored = []
    for e in items:
        s = 0.0
        hay = f"{e.get('mood', '')} {e.get('title', '')} {' '.join(e.get('tags') or [])}".lower()
        if mood:
            s += sum(2 for m in mood.lower().replace(",", " ").split() if m in hay)
        if energy and e.get("energy_level") == energy:
            s += 2
        if lo <= e.get("bpm", 0) <= hi or lo <= e.get("bpm", 0) * 2 <= hi or lo <= e.get("bpm", 0) / 2 <= hi:
            s += 1 if bpm else 0
        if e.get("duration", 0) < min_dur:
            s -= 5
        if "by" in str(e.get("license", "")).lower() and "cc0" not in str(e.get("license", "")).lower():
            s -= 0.2  # credit needed: slight preference for CC0
        scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    print("file | mood | bpm | dur | energy curve (8 bins) | drop s | license")
    for s, e in scored[:top]:
        print(f"{e['file']} | {e.get('mood')} | {e.get('bpm')} | {e.get('duration')} | "
              f"{''.join(' .:-=+*#%@'[min(9, int(v * 9))] for v in e.get('energy', []))} | "
              f"{e.get('drop')} | {e.get('license')}")


def sfx_roles_summary() -> None:
    f = path_of("library") / "sfx.json"
    items = read_json(f) if f.exists() else []
    counts: dict[str, int] = {}
    for e in items:
        counts[e["role"]] = counts.get(e["role"], 0) + 1
    print("SFX by role: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "(empty)"))
    missing = [r for r in SFX_ROLES if r not in counts]
    if missing:
        print("Missing roles (auto SFX will skip these): " + ", ".join(missing))
