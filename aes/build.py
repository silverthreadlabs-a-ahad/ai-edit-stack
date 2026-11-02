"""plan.json  ->  HyperFrames composition (projects/<name>/hf/index.html) + timeline + beat sheet.

The source footage is referenced in place (hardlinked, no re-encode), so building and previewing
cost seconds. Encoding happens only in `aes render`.

Custom work survives rebuilds: anything Claude writes between the CUSTOM markers in index.html
(HTML, CSS and JS) is carried over when the plan is rebuilt.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

from .project import load_units
from .util import (die, fmt_t, info, link_or_copy, load_brand, npx_hf, path_of, project_dir,
                   read_json, slug, step_log, write_json)

TRANSITIONS = {"cut": 0.0, "crossfade": 0.25, "whip": 0.0, "zoom": 0.0, "flash": 0.0}
AUTO_SFX = {"whip": "whoosh", "zoom": "impact", "flash": "impact"}
CUSTOM = {
    "css": ("/* CUSTOM-CSS-START */", "/* CUSTOM-CSS-END */"),
    "html": ("<!-- CUSTOM-HTML-START -->", "<!-- CUSTOM-HTML-END -->"),
    "js": ("// CUSTOM-JS-START", "// CUSTOM-JS-END"),
}


# ---------------------------------------------------------------- helpers


def _custom_blocks(index: Path) -> dict:
    out = {k: "" for k in CUSTOM}
    if not index.exists():
        return out
    txt = index.read_text(encoding="utf-8")
    for k, (a, b) in CUSTOM.items():
        m = re.search(re.escape(a) + r"(.*?)" + re.escape(b), txt, re.S)
        if m:
            out[k] = m.group(1).strip("\n")
    return out


def _snap(t: float, fps: float) -> float:
    return round(round(t * fps) / fps, 4)


def _ensure_hf_project(hf: Path, brand: dict) -> None:
    if (hf / "hyperframes.json").exists():
        return
    w, h = brand["canvas"]["width"], brand["canvas"]["height"]
    res = "portrait" if h > w else ("square" if h == w else "landscape")
    info("  scaffolding HyperFrames project (one time)")
    npx_hf(["init", hf.name, "--example", "blank", "--resolution", res, "--non-interactive",
            "--skip-skills", "--skip-transcribe"], cwd=hf.parent)


def _sfx_pool() -> dict[str, list[dict]]:
    f = path_of("library") / "sfx.json"
    pool: dict[str, list[dict]] = {}
    for e in (read_json(f) if f.exists() else []):
        pool.setdefault(e["role"], []).append(e)
    return pool


def _music_entry(file: str) -> dict:
    f = path_of("library") / "music.json"
    for e in (read_json(f) if f.exists() else []):
        if e["file"] == file or e["file"].endswith(file):
            return e
    p = path_of("library") / file
    if not p.exists():
        die(f"Music file not in library index: {file}. Run: aes library index")
    return {"file": file, "beats": [], "duration": 9999, "title": p.stem, "license": "own/unknown"}


# ---------------------------------------------------------------- main


def build(name: str) -> None:
    d = project_dir(name)
    pj = read_json(d / "project.json")
    if not (d / "plan.json").exists():
        die(f"No plan.json in {d}. The editor writes it (see docs/PLAN_SCHEMA.md).")
    plan = read_json(d / "plan.json")
    brand = load_brand(pj["brand"])
    W, H, FPS = brand["canvas"]["width"], brand["canvas"]["height"], brand["canvas"]["fps"]
    cap = brand["caption"]
    aud = brand["audio"]
    units = {u["gid"]: u for u in load_units(pj)}
    cache = path_of("cache")
    hf = d / "hf"
    with step_log(d, "build"):
        hf.mkdir(exist_ok=True)
        _ensure_hf_project(hf, brand)
        custom = _custom_blocks(hf / "index.html")

        # ---- resolve shots
        shots = []
        for i, s in enumerate(plan.get("shots", [])):
            u = units.get(s["unit"])
            if not u:
                die(f"plan.json shot {i + 1}: unknown unit '{s['unit']}' (see candidates.md)")
            dur_src = u["probe"]["duration"]
            t0 = max(0.0, u["t0"] + float(s.get("trim_in", 0)))
            t1 = min(dur_src, u["t1"] - float(s.get("trim_out", 0)))
            if t1 - t0 < 0.3:
                die(f"plan.json shot {i + 1}: trimmed to {t1 - t0:.2f}s, too short")
            tr = s.get("transition", "cut")
            if tr not in TRANSITIONS:
                die(f"plan.json shot {i + 1}: transition '{tr}' not in {list(TRANSITIONS)}")
            shots.append({"i": i, "unit": u, "t0": t0, "t1": t1, "transition": tr if i else "cut",
                          "zoom": s.get("zoom", "none"), "caption": s.get("caption", True),
                          "emphasis": [w.lower() for w in s.get("emphasis", [])],
                          "reframe_x": s.get("reframe_x"), "caption_text": s.get("caption_text")})
        if not shots:
            die("plan.json has no shots")

        # ---- music + beat grid
        music = plan.get("music")
        m_entry, beats = None, []
        if music:
            m_entry = _music_entry(music["file"])
            mstart = float(music.get("start", 0))
            beats = [b - mstart for b in m_entry.get("beats", []) if b >= mstart]
        window = 0.25

        # ---- lay out timeline (overlaps for crossfades, optional beat snapping)
        def last_word_end(sh):
            u = sh["unit"]
            if u["kind"] != "speech":
                return sh["t0"] + 0.5
            words = _words(cache, u)
            ends = [w[2] for w in words if sh["t0"] - 0.02 <= w[1] and w[2] <= sh["t1"] + 0.05]
            return max(ends) if ends else sh["t0"] + 0.3

        def place(sh, start):
            sh["start"] = _snap(start, FPS)
            sh["dur"] = _snap(sh["t1"] - sh["t0"], FPS)
            sh["end"] = round(sh["start"] + sh["dur"], 4)

        place(shots[0], 0.0)
        for k in range(1, len(shots)):
            sh, prev = shots[k], shots[k - 1]
            ov = TRANSITIONS[sh["transition"]]
            cut = prev["end"] - ov
            if beats and music.get("snap_cuts", True):
                near = min(beats, key=lambda b: abs(b - cut))
                delta = near - cut
                if abs(delta) <= window:
                    src_dur = prev["unit"]["probe"]["duration"]
                    ok = (delta > 0 and prev["t1"] + delta <= src_dur) or \
                         (delta < 0 and prev["t1"] + delta >= last_word_end(prev) + 0.04)
                    if ok:
                        prev["t1"] += delta
                        place(prev, prev["start"])  # re-derive prev end on the frame grid
            place(sh, prev["end"] - ov)
        body_end = shots[-1]["end"]

        # ---- outro
        outro = None
        ob = brand.get("outro")
        if ob and plan.get("outro", True):
            of = Path(ob["file"])
            if not of.exists():
                info(f"  WARNING: outro file missing, skipping: {of}")
            else:
                from .util import ffprobe
                op = ffprobe(of)
                skip = (1.0 / op.get("fps", 30)) if ob.get("skip_first_frame") else 0.0
                ostart = _snap(body_end - ob.get("crossfade_sec", 0), FPS)
                odur = _snap(op["duration"] - skip - 0.02, FPS)
                outro = {"file": of, "start": ostart, "dur": odur, "skip": skip,
                         "hold": ob.get("hold_last_sec", 0), "xf": ob.get("crossfade_sec", 0),
                         "has_audio": op["has_audio"]}
        total = body_end
        if outro:
            total = outro["start"] + outro["dur"] + outro["hold"]
        total = _snap(total, FPS)

        # ---- assets
        assets = hf / "assets"
        src_map = {}
        for sh in shots:
            u = sh["unit"]
            src = Path(u["source"])
            rel = f"assets/src/{u['alias']}{src.suffix.lower()}"
            if rel not in src_map.values():
                link_or_copy(src, hf / rel)
            src_map[u["alias"]] = rel
            sh["src"] = rel

        # ---- elements
        videos, overlays, caps, audios, js, credits = [], [], [], [], [], []
        sfx_pool = _sfx_pool()
        sfx_used: dict[str, int] = {}
        sfx_events = []

        def pick_sfx(role: str):
            pool = sfx_pool.get(role) or (sfx_pool.get("whoosh") if role == "swoosh-text" else None) \
                or (sfx_pool.get("pop") if role in ("ding", "click") else None)
            if not pool:
                return None
            n = sfx_used.get(role, 0)
            sfx_used[role] = n + 1
            return pool[n % len(pool)]

        for k, sh in enumerate(shots):
            u = sh["unit"]
            vid = f"v{k + 1}"
            sh["id"] = vid
            pr = u["probe"]
            src_aspect = pr["width"] / pr["height"]
            face = u.get("face")
            pos_x = sh["reframe_x"] if sh["reframe_x"] is not None else (
                face["cx"] if face and src_aspect > W / H else 0.5)
            speech = u["kind"] == "speech" and pr["has_audio"]
            audio_attr = (f'data-has-audio="true" data-volume="{aud["voice_volume"]}"' if speech
                          else "muted")
            auto = ""
            nxt = shots[k + 1] if k + 1 < len(shots) else None
            xf_in = TRANSITIONS[sh["transition"]] if k else 0
            xf_out = TRANSITIONS[nxt["transition"]] if nxt else (outro["xf"] if outro else 0)
            if speech and (xf_in or xf_out):
                pts = [{"t": 0, "v": 0 if xf_in else 1}]
                if xf_in:
                    pts.append({"t": xf_in, "v": 1})
                if xf_out:
                    pts += [{"t": round(sh["dur"] - xf_out, 3), "v": 1}, {"t": sh["dur"], "v": 0}]
                auto = f" data-automation='{json.dumps({'version': 1, 'lanes': [{'target': 'volume', 'points': pts}]})}'"
            videos.append(
                f'<video id="{vid}" src="{sh["src"]}" data-start="{sh["start"]}" data-duration="{sh["dur"]}" '
                f'data-media-start="{round(sh["t0"], 3)}" data-track-index="{k % 2}" {audio_attr}{auto} '
                f'playsinline style="object-position:{pos_x * 100:.1f}% 50%"></video>')
            st, du = sh["start"], sh["dur"]
            # zoom treatment for the whole shot
            scale = 1.0
            if sh["zoom"] == "punch":
                scale = 1.12
                js.append(f'tl.set("#{vid}", {{scale: 1.12}}, {st});')
            elif sh["zoom"] == "slow":
                scale = 1.06
                js.append(f'tl.fromTo("#{vid}", {{scale: 1}}, {{scale: 1.06, duration: {du}, ease: "none"}}, {st});')
            # transition into this shot
            tr = sh["transition"]
            if k and tr == "crossfade":
                js.append(f'tl.fromTo("#{vid}", {{opacity: 0}}, {{opacity: 1, duration: {xf_in}, ease: "none"}}, {st});')
            elif k and tr == "whip":
                pv = shots[k - 1]["id"]
                js.append(f'tl.to("#{pv}", {{xPercent: -35, filter: "blur(8px)", duration: 0.14, ease: "power2.in"}}, {round(st - 0.14, 3)});')
                js.append(f'tl.fromTo("#{vid}", {{xPercent: 35, filter: "blur(8px)"}}, {{xPercent: 0, filter: "blur(0px)", duration: 0.18, ease: "power3.out"}}, {st});')
            elif k and tr == "zoom":
                js.append(f'tl.fromTo("#{vid}", {{scale: {round(scale * 1.25, 3)}}}, {{scale: {scale}, duration: 0.3, ease: "power3.out"}}, {st});')
            elif k and tr == "flash":
                fid = f"flash{k}"
                overlays.append(f'<div id="{fid}" class="flash clip" data-start="{round(st - 0.08, 3)}" data-duration="0.2"></div>')
                js.append(f'tl.fromTo("#{fid}", {{opacity: 0}}, {{opacity: 0.85, duration: 0.06, yoyo: true, repeat: 1, ease: "power1.inOut"}}, {round(st - 0.08, 3)});')
            if k and tr in AUTO_SFX:
                sfx_events.append({"at": st, "role": AUTO_SFX[tr], "align": "peak", "why": f"{tr} into shot {k + 1}"})

            # captions
            if sh["caption"] and u["kind"] == "speech":
                y = cap["y_normal"]
                if face:
                    fb = (face["bottom"] * H - H / 2) * scale + H / 2
                    if fb + 40 > cap["y_normal"]:
                        y = cap["y_low"] if fb + 40 <= cap["y_low"] else cap["y_top"]
                sh["caption_y"] = y
                for c in _chunks(_words(cache, u), sh, cap["max_words"], FPS):
                    cid = f"cap{len(caps) + 1}"
                    spans = []
                    for w in c["words"]:
                        clean = re.sub(r"[\.,!?;:\"]+$", "", w).strip()
                        cls = ' class="acc"' if clean.lower().strip("'\"") in sh["emphasis"] else ""
                        spans.append(f"<span{cls}>{html.escape(clean)}</span>")
                    caps.append(f'<div id="{cid}" class="cap clip" data-start="{c["start"]}" '
                                f'data-duration="{c["dur"]}" data-track-index="3" style="top:{y}px">'
                                + " ".join(spans) + "</div>")
                    sh.setdefault("captions", []).append(" ".join(c["words"]))
                    p = cap["pop"]
                    js.append(f'tl.from("#{cid}", {{scale: {p["from_scale"]}, y: {p["from_y"]}, opacity: 0, '
                              f'duration: {p["duration"]}, ease: "{p["ease"]}"}}, {c["start"]});')

        # hook + kinetic texts
        kin = brand["kinetic"]
        texts = list(plan.get("texts", []))
        if plan.get("hook") and plan["hook"].get("text"):
            texts.insert(0, {"at": 0.0, "dur": plan["hook"].get("dur", 1.6), "text": plan["hook"]["text"],
                             "y": plan["hook"].get("y", kin["y"]),
                             "style": "kinetic", "sfx": plan["hook"].get("sfx", "impact")})
        for n, t in enumerate(texts):
            tid = f"txt{n + 1}"
            at, du = _snap(float(t["at"]), FPS), _snap(float(t.get("dur", 1.6)), FPS)
            y = t.get("y", kin["y"])
            overlays.append(f'<div id="{tid}" class="kin clip" data-start="{at}" data-duration="{round(du - 0.004, 4)}" '
                            f'data-track-index="4" style="top:{y}px">{html.escape(t["text"])}</div>')
            js.append(f'tl.from("#{tid}", {{yPercent: 60, opacity: 0, duration: 0.28, ease: "power3.out"}}, {at});')
            role = t.get("sfx", "swoosh-text")
            if role and role != "none":
                sfx_events.append({"at": at, "role": role, "align": "end" if role == "riser" and at > 2 else "start",
                                   "why": f"text '{t['text'][:24]}'"})

        # outro elements
        if outro:
            rel = "assets/outro" + outro["file"].suffix.lower()
            link_or_copy(outro["file"], hf / rel)
            a_attr = 'data-has-audio="true" data-volume="1"' if outro["has_audio"] else "muted"
            videos.append(f'<video id="outro" src="{rel}" data-start="{outro["start"]}" data-duration="{outro["dur"]}" '
                          f'data-media-start="{round(outro["skip"], 4)}" data-track-index="2" {a_attr} playsinline></video>')
            if outro["xf"]:
                js.append(f'tl.fromTo("#outro", {{opacity: 0}}, {{opacity: 1, duration: {outro["xf"]}, ease: "none"}}, {outro["start"]});')
            if outro["hold"]:
                png = hf / "assets" / "outro_last.png"
                if not png.exists():
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.15", "-i", str(outro["file"]),
                                    "-frames:v", "1", str(png)])
                videos.append(f'<img id="outro-hold" class="clip hold" src="assets/outro_last.png" '
                              f'data-start="{round(outro["start"] + outro["dur"], 4)}" data-duration="{outro["hold"]}" '
                              f'data-track-index="2" alt="">')

        # music
        if music and m_entry:
            mfile = path_of("library") / m_entry["file"]
            rel = f"assets/music/{slug(Path(m_entry['file']).stem)}{mfile.suffix.lower()}"
            link_or_copy(mfile, hf / rel)
            mstart = float(music.get("start", 0))
            m_end = total if (not outro or ob.get("music_through")) else outro["start"] + max(outro["xf"], 0.25)
            m_dur = _snap(min(m_end, m_entry.get("duration", 9999) - mstart), FPS)
            vol = music.get("volume", aud["music_volume"])
            boost = aud.get("music_gap_boost", 1.0)
            fade = ob.get("music_fade_out_sec", 1.5) if ob else 1.5
            pts = [{"t": 0, "v": 0 if mstart > 0 else 1}, {"t": 0.4, "v": 1}]
            for g0, g1 in _speech_gaps(shots, body_end):
                if g1 - g0 >= 1.0 and g1 < m_dur - fade:
                    pts += [{"t": round(g0, 3), "v": 1}, {"t": round(g0 + 0.25, 3), "v": boost},
                            {"t": round(g1 - 0.25, 3), "v": boost}, {"t": round(g1, 3), "v": 1}]
            pts += [{"t": round(max(0.5, m_dur - fade), 3), "v": 1}, {"t": m_dur, "v": 0}]
            pts = _clean_points(pts)
            audios.append(f'<audio id="music" src="{rel}" data-start="0" data-duration="{m_dur}" '
                          f'data-media-start="{mstart}" data-volume="{vol}" data-track-index="10" '
                          f"data-automation='{json.dumps({'version': 1, 'lanes': [{'target': 'volume', 'points': pts}]})}'></audio>")
            credits.append(m_entry)

        # sfx (auto or explicit)
        sfx_spec = plan.get("sfx", "auto")
        events = sfx_events if sfx_spec == "auto" else ([] if sfx_spec in ("none", None) else sfx_spec)
        placed = []
        for n, ev in enumerate(events):
            e = None
            if "file" in ev:
                e = next((x for v in sfx_pool.values() for x in v if x["file"].endswith(ev["file"])), None)
            else:
                e = pick_sfx(ev["role"])
            if not e:
                continue
            at = float(ev["at"])
            if ev.get("align") == "peak":
                at -= e.get("peak", 0)
            elif ev.get("align") == "end":
                at -= e["duration"]
            at = max(0.0, _snap(at, FPS))
            sid = f"sfx{n + 1}"
            rel = f"assets/sfx/{e['role']}-{slug(Path(e['file']).stem)}{Path(e['file']).suffix.lower()}"
            link_or_copy(path_of("library") / e["file"], hf / rel)
            audios.append(f'<audio id="{sid}" src="{rel}" data-start="{at}" data-duration="{_snap(e["duration"], FPS) or 0.5}" '
                          f'data-volume="{ev.get("volume", aud["sfx_volume"])}" data-track-index="{11 + n % 4}"></audio>')
            placed.append({"at": at, "hit": round(float(ev["at"]), 3), "role": e["role"], "file": e["file"],
                           "why": ev.get("why", "")})
            credits.append(e)

        # ---- write index.html
        tpl = (Path(__file__).resolve().parent.parent / "templates" / "composition.html").read_text(encoding="utf-8")
        acc = {"color": f"color:{brand['colors']['accent']};",
               "underline": f"text-decoration:underline;text-decoration-color:{brand['colors']['accent']};"
                            f"text-decoration-thickness:8px;text-underline-offset:10px;",
               "serif": f"font-family:{cap['serif_accent_font']};font-style:italic;text-transform:none;font-weight:400;"}
        kin_style = "font-style:italic;" if kin.get("italic") else ""
        out = (tpl.replace("{{W}}", str(W)).replace("{{H}}", str(H)).replace("{{FPS}}", str(FPS))
               .replace("{{DURATION}}", str(total)).replace("{{TITLE}}", html.escape(plan.get("title", name)))
               .replace("{{FONTS_CSS}}", brand["fonts_css"])
               .replace("{{GROUND}}", brand["colors"]["ground"]).replace("{{INK}}", brand["colors"]["ink"])
               .replace("{{CAP_FONT}}", cap["font"]).replace("{{CAP_WEIGHT}}", str(cap["weight"]))
               .replace("{{CAP_SIZE}}", str(cap["size"]))
               .replace("{{CAP_TRANSFORM}}", "uppercase" if cap.get("uppercase") else "none")
               .replace("{{CAP_SHADOW}}", cap.get("shadow", "none"))
               .replace("{{ACCENT_CSS}}", acc.get(cap.get("accent_style", "color"), acc["color"]))
               .replace("{{KIN_FONT}}", kin["font"]).replace("{{KIN_WEIGHT}}", str(kin["weight"]))
               .replace("{{KIN_SIZE}}", str(kin["size"])).replace("{{KIN_EXTRA}}", kin_style)
               .replace("{{VIDEOS}}", "\n      ".join(videos))
               .replace("{{OVERLAYS}}", "\n        ".join(overlays))
               .replace("{{CAPTIONS}}", "\n        ".join(caps))
               .replace("{{AUDIO}}", "\n      ".join(audios))
               .replace("{{JS}}", "\n      ".join(js))
               .replace("{{CUSTOM_CSS}}", custom["css"]).replace("{{CUSTOM_HTML}}", custom["html"])
               .replace("{{CUSTOM_JS}}", custom["js"]))
        (hf / "index.html").write_text(out, encoding="utf-8")

        # ---- timeline + beat sheet + credits
        timeline = {"duration": total, "fps": FPS, "body_end": body_end,
                    "shots": [{"n": s["i"] + 1, "id": s["id"], "unit": s["unit"]["gid"], "start": s["start"],
                               "end": s["end"], "src": [round(s["t0"], 3), round(s["t1"], 3)],
                               "transition": s["transition"], "zoom": s["zoom"],
                               "caption_y": s.get("caption_y"), "captions": s.get("captions", []),
                               "desc": s["unit"].get("desc") or s["unit"].get("text", "")[:80]}
                              for s in shots],
                    "texts": texts, "sfx": placed,
                    "music": {"file": m_entry["file"], "start": music.get("start", 0)} if m_entry else None,
                    "outro": {"start": outro["start"], "end": round(outro["start"] + outro["dur"] + outro["hold"], 3)}
                    if outro else None}
        write_json(d / "timeline.json", timeline)
        _beatsheet(d, timeline, m_entry)
        _credits(d, credits)
        info(f"Built {hf / 'index.html'}  ({len(shots)} shots, {total:.1f}s, {len(placed)} sfx, "
             f"{len(caps)} caption chunks)")
        res = npx_hf(["lint", "."], cwd=hf, check=False)
        txt = (res.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        info("  lint: " + (" | ".join(txt[-4:]) if txt else f"exit {res.returncode}"))


# ---------------------------------------------------------------- pieces


_WORDS_CACHE: dict[str, list] = {}


def _words(cache: Path, u: dict) -> list:
    key = u["cache"]
    if key not in _WORDS_CACHE:
        f = cache / key / "transcript.json"
        _WORDS_CACHE[key] = read_json(f)["words"] if f.exists() else []
    return _WORDS_CACHE[key]


def _chunks(words: list, sh: dict, max_words: int, fps: float) -> list[dict]:
    t0, t1, st = sh["t0"], sh["t1"], sh["start"]
    ws = [w for w in words if t0 - 0.02 <= (w[1] + w[2]) / 2 <= t1 + 0.02 and w[0]]
    override = sh.get("caption_text")
    if override and ws:
        # Re-time the editor's text (e.g. romanized Hindi/Urdu, a spelling fix) over the spoken timings
        # spread the new words over the spoken span, in proportion to their length
        new = override.split()
        a, b = ws[0][1], ws[-1][2]
        weights = [len(w) + 2 for w in new]
        tot, acc, timed = sum(weights), 0, []
        for w, wt in zip(new, weights):
            s = a + (b - a) * acc / tot
            acc += wt
            timed.append([w, round(s, 3), round(a + (b - a) * acc / tot, 3), 1.0])
        ws = timed
    groups, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        gap = ws[i + 1][1] - w[2] if i + 1 < len(ws) else 9
        if len(cur) >= max_words or re.search(r"[\.!?,;:]$", w[0]) or gap > 0.35:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    shot_end = st + sh["dur"] - 1.0 / fps
    for k, g in enumerate(groups):
        a = _snap(st + max(0.0, g[0][1] - t0), fps)
        nxt = _snap(st + (groups[k + 1][0][1] - t0), fps) if k + 1 < len(groups) else None
        end = st + (g[-1][2] - t0) + 0.25
        if nxt is not None and nxt - (st + g[-1][2] - t0) < 0.6:
            end = nxt
        end = min(end, shot_end)
        if end - a < 0.1:
            continue
        out.append({"start": a, "dur": round(end - a - 0.004, 4), "words": [w[0] for w in g]})
    return out


def _speech_gaps(shots: list, body_end: float):
    """Timeline spans with no speech (b-roll), used to lift the music bed."""
    spans = sorted((s["start"], s["end"]) for s in shots if s["unit"]["kind"] == "speech")
    t = 0.0
    for a, b in spans:
        if a > t:
            yield (t, a)
        t = max(t, b)
    if body_end > t:
        yield (t, body_end)


def _clean_points(pts: list) -> list:
    pts = sorted(pts, key=lambda p: p["t"])
    out = []
    for p in pts:
        if out and p["t"] <= out[-1]["t"]:
            p = {"t": round(out[-1]["t"] + 0.01, 3), "v": p["v"]}
        out.append(p)
    return out


def _beatsheet(d: Path, tl: dict, m_entry) -> None:
    L = [f"# Beat sheet ({tl['duration']:.1f}s)", "",
         "| # | time | shot | on screen | captions | in-transition | sfx |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for s in tl["shots"]:
        sfx = ", ".join(f"{x['role']}@{x['hit']:.2f}" for x in tl["sfx"] if s["start"] - 0.05 <= x["hit"] < s["end"] - 0.05)
        caps = " / ".join(s["captions"])[:90]
        L.append(f"| {s['n']} | {fmt_t(s['start'])}-{fmt_t(s['end'])} | {s['unit']} | {s['desc'][:60]} | "
                 f"{caps} | {s['transition']}{' +' + s['zoom'] if s['zoom'] != 'none' else ''} | {sfx or '-'} |")
    if tl["texts"]:
        L += ["", "Texts: " + "; ".join(f"{t['at']}s '{t['text']}'" for t in tl["texts"])]
    if m_entry:
        L += ["", f"Music: {m_entry['file']} from {tl['music']['start']}s, {m_entry.get('bpm')} bpm, "
                  f"license {m_entry.get('license')}"]
    if tl["outro"]:
        L += [f"Outro: {tl['outro']['start']}s to {tl['outro']['end']}s"]
    (d / "beatsheet.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _credits(d: Path, items: list) -> None:
    lines = sorted({e.get("attribution") for e in items
                    if e.get("attribution") and "cc0" not in str(e.get("license", "")).lower()})
    (d / "CREDITS.txt").write_text(("Credits (CC BY, include in the post caption):\n" + "\n".join(lines) + "\n")
                                   if lines else "No attribution required (CC0 / own assets).\n",
                                   encoding="utf-8")
