"""Projects, the compact candidate list the editor reads, and cached visual descriptions."""

from __future__ import annotations

import difflib
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
        cdirs = analyze_sources(sources, force=force)
    pj["clips"] = [{"alias": f"c{i + 1:02d}", "cache": c.name, "name": s.name, "source": str(s)}
                   for i, (s, c) in enumerate(zip(sources, cdirs)) if (c / "analysis.json").exists()]
    write_json(d / "project.json", pj)
    write_candidates(name)


def load_units(pj: dict) -> list[dict]:
    """All units of the project with global ids (c01-u004) and cached descriptions."""
    cache = path_of("cache")
    out = []
    for c in pj["clips"]:
        a = read_json(cache / c["cache"] / "analysis.json")
        dfile = cache / c["cache"] / "descriptions.json"
        desc = read_json(dfile) if dfile.exists() else {}
        for u in a["units"]:
            g = dict(u)
            g["gid"] = f"{c['alias']}-{u['id']}"
            g["alias"] = c["alias"]
            g["cache"] = c["cache"]
            g["source"] = a["source"]
            g["probe"] = a["probe"]
            g["desc"] = desc.get(u["id"])
            out.append(g)
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
    broll = sorted((u for u in units if u["kind"] == "broll" and not bad & set(u.get("flags", []))),
                   key=lambda u: -u.get("q", 0))
    hidden = sum(1 for u in units if u["kind"] == "broll" and bad & set(u.get("flags", [])))
    broll_top = broll[:mode["max_broll_candidates"]]

    L = [f"# Candidates: {name}", "",
         f"brand={pj['brand']} mode={pj['mode']} format={pj['format']}", "",
         "## Source clips"]
    for c in pj["clips"]:
        a = read_json(path_of("cache") / c["cache"] / "analysis.json")
        p = a["probe"]
        L.append(f"- {c['alias']} = {c['name']} ({p['duration']:.1f}s, {p.get('width')}x{p.get('height')}, "
                 f"{p.get('fps')}fps, lang={a.get('language')})")
    L += ["", "## Speech units (chronological)",
          "id | src s | dur | q | face | flags | text"]
    for u in speech:
        fl = ",".join(u.get("flags", [])) or "-"
        L.append(f"{u['gid']} | {u['t0']:.2f}-{u['t1']:.2f} | {u['dur']:.1f} | {u.get('q', 0)} | "
                 f"{_face_label(u.get('face'))} | {fl} | {u.get('text', '')}")
    L += ["", f"## B-roll units (top {len(broll_top)} of {len(broll)} by quality; {hidden} rejected as blurry/dark)",
          "id | src s | dur | q | motion | description"]
    for u in broll_top:
        L.append(f"{u['gid']} | {u['t0']:.2f}-{u['t1']:.2f} | {u['dur']:.1f} | {u.get('q', 0)} | "
                 f"{u.get('motion', 0)} | {u.get('desc') or '(not described yet)'}")
    out = d / "candidates.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(d / "candidates.json", {"speech": [u["gid"] for u in speech],
                                       "broll": [u["gid"] for u in broll_top]})
    info(f"Wrote {out}  ({len(speech)} speech, {len(broll_top)} b-roll candidates)")
    return out


# ---------------------------------------------------------------- descriptions


def describe_pending(name: str) -> Path:
    """List units that still need a one-line visual description (cached forever once done)."""
    d = project_dir(name)
    pj = read_json(d / "project.json")
    cfg = load_config()
    mode = cfg["modes"][pj["mode"]]
    cand = read_json(d / "candidates.json")
    want = set(cand["broll"])
    if mode["describe_speech_units"]:
        want |= set(cand["speech"])
    units = {u["gid"]: u for u in load_units(pj)}
    pending = []
    for gid in sorted(want):
        u = units.get(gid)
        if u and not u.get("desc"):
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
