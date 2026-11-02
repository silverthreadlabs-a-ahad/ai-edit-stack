"""Projects, the compact candidate list the editor reads, and cached visual descriptions."""

from __future__ import annotations

import difflib
import re
import shutil
import time
from pathlib import Path

from .analyze import analyze_sources, list_sources
from .util import (ROOT, die, info, load_brand, load_config, path_of, project_dir, read_json,
                   step_log, write_json)

# ---------------------------------------------------------------- create


def new_project(name: str, brand: str, mode: str, source: str | None, fmt: str) -> Path:
    cfg = load_config()
    if mode not in cfg["modes"]:
        die(f"Unknown mode '{mode}'. Use one of: {', '.join(cfg['modes'])}")
    load_brand(brand)  # validates
    d = path_of("projects") / name
    if d.exists():
        die(f"Project already exists: {d}")
    src = Path(source) if source else path_of("inbox") / name
    if not src.is_absolute():
        src = (ROOT / src) if (ROOT / src).exists() else src.resolve()
    brief = (ROOT / "templates" / "BRIEF.template.md").read_text(encoding="utf-8")
    d.mkdir(parents=True)
    brief = brief.replace("{{name}}", name).replace("{{brand}}", brand).replace("{{mode}}", mode) \
                 .replace("{{format}}", fmt)
    (d / "BRIEF.md").write_text(brief, encoding="utf-8")
    write_json(d / "project.json", {"name": name, "brand": brand, "mode": mode, "format": fmt,
                                    "source": str(src), "created": time.strftime("%Y-%m-%d %H:%M"),
                                    "clips": []})
    info(f"Created {d}")
    info(f"  source folder: {src}{'' if src.exists() else '  (does not exist yet: put clips there)'}")
    info(f"  next: fill in {d / 'BRIEF.md'}, then run: aes analyze {name}")
    return d


# ---------------------------------------------------------------- analyze + candidates


def analyze_project(name: str, force: bool = False) -> None:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    sources = list_sources(Path(pj["source"]))
    with step_log(d, "analyze", clips=len(sources)):
        cdirs = analyze_sources(sources, force=force, language=load_brand(pj["brand"]).get("language"))
    pj["clips"] = [{"alias": f"c{i + 1:02d}", "cache": c.name, "name": s.name, "source": str(s)}
                   for i, (s, c) in enumerate(zip(sources, cdirs)) if (c / "analysis.json").exists()]
    write_json(d / "project.json", pj)
    write_candidates(name)


# ---------------------------------------------------------------- clip roles (VO vs b-roll)

COUNT_IN = {
    "1", "2", "3", "4", "5", "one", "two", "three", "four", "five", "go", "action", "ready", "ok", "okay",
    "yeah", "yes", "cut", "rolling", "and", "start", "rec", "track", "that's", "it", "it?",
    "त्री", "टू", "वन", "वान", "ओन", "गो", "गू", "यू", "एक", "दो", "तीन", "चलो", "शुरू", "एक्शन", "ठीक", "हाँ",
    "ایک", "دو", "تین", "گو", "ایکشن", "اکشن", "بس", "ٹھیک", "ہاں", "چلو",
}


def _script(ch: str) -> str:
    import unicodedata
    try:
        return unicodedata.name(ch).split(" ")[0]
    except ValueError:
        return "?"


def _clean_ratio(words: list[str]) -> float:
    """Share of words written in a single script (whisper garbage mixes scripts inside a word)."""
    if not words:
        return 0.0
    ok = 0
    for w in words:
        sc = {_script(c) for c in w if c.isalpha()}
        ok += len(sc) <= 1
    return ok / len(words)


def _norm(w: str) -> str:
    return re.sub(r"[\.,!?;:\"'\-…।]+", "", w.lower()).strip()


def _is_count_in(text: str) -> bool:
    ws = [_norm(w) for w in text.split()]
    ws = [w for w in ws if w]
    return not ws or all(w in COUNT_IN or w.isdigit() for w in ws)


DIRECTIONS = {
    # English / romanized
    "look", "camera", "turn", "side", "smile", "hood", "hands", "hand", "pocket", "pockets", "up", "down",
    "left", "right", "walk", "stop", "again", "relax", "chin", "ok", "okay", "action", "cut", "yes",
    "upar", "neeche", "theek", "thik", "mud", "ghoom", "haath", "chalo", "haan", "phir", "dobara",
    # Devanagari
    "लुक", "कैमरा", "कैमरे", "टर्न", "टन", "साइड", "स्माइल", "हुड", "होड़ी", "हाथ", "ऊपर", "अपर", "उपर", "नीचे",
    "निचे", "ठीक", "मुड़", "मुड़ो", "घूम", "गूम", "चलो", "हाँ", "हां", "फिर", "दोबारा", "फोल्ड", "यस", "ओके",
    "एक्शन", "कट", "तरफ",
    # Urdu
    "کیمرے", "کیمرا", "ہاتھ", "اوپر", "نیچے", "ٹھیک", "مڑو", "ہاں", "پھر", "دوبارہ", "طرف",
}


def _direction_score(text: str) -> float:
    """Share of the line that sounds like a director talking: direction words plus repeated phrases."""
    ws = [_norm(w) for w in text.split()]
    ws = [w for w in ws if w]
    if not ws:
        return 1.0
    hits = sum(w in DIRECTIONS for w in ws)
    bigrams = list(zip(ws, ws[1:]))
    rep = len(bigrams) - len(set(bigrams))
    return (hits + rep) / len(ws)


def _is_vo(u: dict) -> bool:
    """A real voiceover / to-camera line: enough clean words, steady pace, a face on screen."""
    ws = u.get("text", "").split()
    if len(ws) < 8 or _is_count_in(u.get("text", "")):
        return False
    rate = len(ws) / max(0.1, u["dur"])
    conf = u.get("conf")
    return (_clean_ratio(ws) >= 0.9 and rate >= 1.6 and bool(u.get("face"))
            and (conf is None or conf >= 0.65) and _direction_score(u.get("text", "")) < 0.2)


def _assign_roles(units: list[dict]) -> None:
    """Clips with no real voiceover line are b-roll takes (director count-ins, directions):
    their speech units become muted b-roll so they are judged on the picture only."""
    by_clip: dict[str, list[dict]] = {}
    for u in units:
        by_clip.setdefault(u["alias"], []).append(u)
    for alias, us in by_clip.items():
        vo = [u for u in us if u["kind"] == "speech" and _is_vo(u)]
        for u in us:
            if u in vo:
                u["role"] = "vo"
            elif u["kind"] == "speech" and not vo:
                u["kind"] = "broll"
                u["role"] = "take"
                u["was_speech"] = True
                u["flags"] = [f for f in u.get("flags", []) if f not in ("no-face", "shaky")]
            else:
                u["role"] = "speech" if u["kind"] == "speech" else "broll"


def load_units(pj: dict) -> list[dict]:
    """All units of the project with global ids (c01-u004) and cached descriptions."""
    cache = path_of("cache")
    out = []
    for c in pj["clips"]:
        a = read_json(cache / c["cache"] / "analysis.json")
        dfile = cache / c["cache"] / "descriptions.json"
        desc = read_json(dfile) if dfile.exists() else {}
        tgfile = cache / c["cache"] / "tags.json"
        tags = read_json(tgfile) if tgfile.exists() else {}
        tfile = cache / c["cache"] / "transcript.json"
        words = read_json(tfile)["words"] if tfile.exists() else []
        for u in a["units"]:
            g = dict(u)
            g["gid"] = f"{c['alias']}-{u['id']}"
            g["alias"] = c["alias"]
            g["cache"] = c["cache"]
            g["source"] = a["source"]
            g["probe"] = a["probe"]
            g["desc"] = desc.get(u["id"]) or desc.get("_clip") or tags.get(u["id"])
            g["has_haiku_desc"] = bool(desc.get(u["id"]) or desc.get("_clip"))
            g["n_scenes"] = len(a.get("scenes", [])) or 1
            if u.get("w") and words:
                ws = words[u["w"][0]:u["w"][1]]
                ps = [w[3] for w in ws if len(w) > 3]
                g["conf"] = round(sum(ps) / len(ps), 3) if ps else None
            out.append(g)
    _assign_roles(out)
    return out


def _filler_count(text: str, fillers: set[str]) -> int:
    return sum(1 for w in text.lower().replace(",", " ").replace(".", " ").split() if w in fillers)


def _face_label(f):
    if not f:
        return "-"
    pos = "high" if f["cy"] < 0.38 else ("low" if f["cy"] > 0.58 else "mid")
    return f"{pos}/{int(f['h'] * 100)}%"


def write_candidates(name: str) -> Path:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    cfg = load_config()
    mode = cfg["modes"][pj["mode"]]
    q = cfg["quality"]
    fillers = set(q["filler_words"])
    units = load_units(pj)
    speech = [u for u in units if u["kind"] == "speech"]
    # retakes: a phrase repeated soon after is usually re-done; keep the later take
    for i, u in enumerate(speech):
        a = u.get("text", "").lower()
        for v in speech[i + 1:i + 9]:
            if difflib.SequenceMatcher(None, a, v.get("text", "").lower()).ratio() >= q["retake_similarity"]:
                u.setdefault("flags", []).append(f"retake->{v['gid']}")
                break
        n = _filler_count(u.get("text", ""), fillers)
        if n:
            u.setdefault("flags", []).append(f"filler:{n}")
    bad = {"blurry", "dark", "blown", "unreadable"}
    # b-roll grouped per clip: one row per take, best unit first (a take is usually one scene)
    clips: dict[str, list[dict]] = {}
    for u in units:
        if u["kind"] == "broll":
            clips.setdefault(u["alias"], []).append(u)
    groups = []
    for alias, us in clips.items():
        us.sort(key=lambda u: -u.get("q", 0))
        good = [u for u in us if not bad & set(u.get("flags", []))]
        groups.append({"alias": alias, "units": us, "good": good, "best": (good or us)[0]})
    shown = sorted((g for g in groups if g["good"]), key=lambda g: -g["best"].get("q", 0))
    hidden = [g for g in groups if not g["good"]]
    shown = shown[:mode["max_broll_candidates"]]
    vo = [u for u in speech if u.get("role") == "vo"]

    L = [f"# Candidates: {name}", "",
         f"brand={pj['brand']} mode={pj['mode']} format={pj['format']}", "",
         "## Source clips"]
    for c in pj["clips"]:
        a = read_json(path_of("cache") / c["cache"] / "analysis.json")
        p = a["probe"]
        L.append(f"- {c['alias']} = {c['name']} ({p['duration']:.1f}s, {p.get('width')}x{p.get('height')}, "
                 f"{p.get('fps')}fps, lang={a.get('language')})")
    if vo:
        L += ["", "## Voiceover / to-camera takes (auto-detected)",
              "id | src s | dur | q | conf | face | flags | text"]
        for u in vo:
            fl = ",".join(u.get("flags", [])) or "-"
            L.append(f"{u['gid']} | {u['t0']:.2f}-{u['t1']:.2f} | {u['dur']:.1f} | {u.get('q', 0)} | "
                     f"{u.get('conf')} | {_face_label(u.get('face'))} | {fl} | {u.get('text', '')}")
    other = [u for u in speech if u.get("role") != "vo"]
    if other:
        L += ["", "## Other speech units (chronological)",
              "id | src s | dur | q | face | flags | text"]
        for u in other:
            fl = ",".join(u.get("flags", [])) or "-"
            L.append(f"{u['gid']} | {u['t0']:.2f}-{u['t1']:.2f} | {u['dur']:.1f} | {u.get('q', 0)} | "
                     f"{_face_label(u.get('face'))} | {fl} | {u.get('text', '')}")
    n_takes = sum(1 for g in groups if g["units"][0].get("was_speech"))
    L += ["", f"## B-roll by clip (top {len(shown)} of {len(groups)} clips by best unit; "
              f"{len(hidden)} clips rejected as blurry/dark; {n_takes} clips were director takes, audio muted)",
          "clip | best unit | src s | q | motion | flags | other units (q) | description"]
    for g in shown:
        b = g["best"]
        rest = " ".join(f"{u['id']}({u.get('q', 0)})" for u in g["good"][1:])[:80] or "-"
        fl = ",".join(b.get("flags", [])) or "-"
        L.append(f"{g['alias']} | {b['gid']} | {b['t0']:.2f}-{b['t1']:.2f} | {b.get('q', 0)} | "
                 f"{b.get('motion', 0)} | {fl} | {rest} | {b.get('desc') or '(not described yet)'}")
    if hidden:
        L += ["", "Rejected clips: " + ", ".join(f"{g['alias']}({','.join(g['best'].get('flags', []))})" for g in hidden)]
    out = d / "candidates.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(d / "candidates.json", {
        "speech": [u["gid"] for u in speech], "vo": [u["gid"] for u in vo],
        "broll": [u["gid"] for g in shown for u in g["good"]],
        # what to describe: the best unit of a one-scene take stands for the whole clip
        "describe": [u["gid"] for g in shown
                     for u in ([g["best"]] if g["best"]["n_scenes"] == 1 else g["good"])]})
    info(f"Wrote {out}  ({len(vo)} voiceover, {len(speech) - len(vo)} other speech, "
         f"{len(shown)} b-roll clips)")
    return out


# ---------------------------------------------------------------- descriptions


def describe_pending(name: str) -> Path:
    """List units that still need a one-line visual description (cached forever once done)."""
    d = project_dir(name)
    pj = read_json(d / "project.json")
    cfg = load_config()
    mode = cfg["modes"][pj["mode"]]
    cand = read_json(d / "candidates.json")
    want = list(cand.get("describe", cand["broll"]))
    eng = cfg.get("describe", {}).get("engine", "haiku")
    if eng in ("local", "hybrid"):
        all_units = {u["gid"]: u for u in load_units(pj)}
        tagged = [g for g in want if (all_units.get(g) or {}).get("desc", "") .startswith("auto:")]
        if eng == "local":
            want = [g for g in want if g not in tagged]
        else:  # Haiku only for the best clips; local tags cover the rest
            n = cfg["describe"].get("haiku_top", 15)
            best = sorted(want, key=lambda g: -(all_units.get(g) or {}).get("q", 0))[:n]
            want = [g for g in want if g in best or g not in tagged]
    want = set(want)
    if mode["describe_speech_units"]:
        want |= set(cand["speech"])
    units = {u["gid"]: u for u in load_units(pj)}
    pending = []
    for gid in sorted(want):
        u = units.get(gid)
        if u and not u.get("has_haiku_desc"):
            sheet = path_of("cache") / u["cache"] / "sheets" / f"{u['id']}.jpg"
            if sheet.exists():
                pending.append({"id": gid, "sheet": str(sheet)})
    out = d / "describe_pending.json"
    write_json(out, pending)
    info(f"{len(pending)} units need descriptions -> {out}")
    return out


def describe_apply(name: str, file: str) -> None:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    data = read_json(Path(file))
    alias = {c["alias"]: c["cache"] for c in pj["clips"]}
    by_cache: dict[str, dict] = {}
    for gid, text in data.items():
        a, uid = gid.split("-", 1)
        if a not in alias:
            continue
        by_cache.setdefault(alias[a], {})[uid] = str(text).strip()[:200]
    n = 0
    for cache, items in by_cache.items():
        f = path_of("cache") / cache / "descriptions.json"
        cur = read_json(f) if f.exists() else {}
        cur.update(items)
        an = path_of("cache") / cache / "analysis.json"
        if an.exists() and len(read_json(an).get("scenes", [])) <= 1 and "_clip" not in cur:
            cur["_clip"] = next(iter(items.values()))
        n += len(items)
        write_json(f, cur)
    info(f"Stored {n} descriptions in the cache")
    write_candidates(name)


# ---------------------------------------------------------------- status


def status(name: str) -> None:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    info(f"{name}: brand={pj['brand']} mode={pj['mode']} clips={len(pj['clips'])}")
    for f in ["BRIEF.md", "candidates.md", "plan.json", "hf/index.html", "beatsheet.md",
              "framesheet.jpg"]:
        info(f"  {'[x]' if (d / f).exists() else '[ ]'} {f}")
    renders = sorted((d / "renders").glob("*.mp4")) if (d / "renders").exists() else []
    info(f"  renders: {len(renders)}" + (f" (latest {renders[-1].name})" if renders else ""))
    log = d / "runlog.jsonl"
    if log.exists():
        import json
        tot: dict[str, float] = {}
        for line in log.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            tot[r["step"]] = tot.get(r["step"], 0) + r["seconds"]
        info("  time spent: " + ", ".join(f"{k} {v:.0f}s" for k, v in tot.items())
             + f" | total {sum(tot.values()) / 60:.1f} min")


def clean_cache(dry: bool = True) -> None:
    """Remove cache entries whose source file no longer exists."""
    for c in path_of("cache").iterdir():
        a = c / "analysis.json"
        if a.exists() and not Path(read_json(a)["source"]).exists():
            info(f"{'would remove' if dry else 'removing'} {c.name}")
            if not dry:
                shutil.rmtree(c)
