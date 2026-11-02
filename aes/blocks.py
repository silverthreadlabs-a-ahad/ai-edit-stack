"""Reusable graphic blocks for plan.json `graphics[]` (no hand-written HTML/CSS/JS needed).

Types: badge, arrow_label, highlight_word, phone_reels, gag, cta. Each one is placed with `at`
(timeline seconds) or `at_word` (+ optional `shot`, `nth`, `offset`), so it locks to the voice.
Every block can carry `"sfx": "<role>" | "none"` (defaults below) and `dur`.
"""

from __future__ import annotations

import html
import re

DEFAULT_SFX = {"badge": "pop", "arrow_label": "whoosh", "highlight_word": "pop",
               "phone_reels": "whoosh", "gag": "none", "cta": "whoosh"}
GAG_FX = {"dark": "brightness(0.45)", "blur": "blur(12px)", "bw": "grayscale(1)", "pop": "contrast(1.25) saturate(1.3)"}
GAG_ZERO = {"dark": "brightness(1)", "blur": "blur(0px)", "bw": "grayscale(0)", "pop": "contrast(1) saturate(1)"}


def norm(w: str) -> str:
    return re.sub(r"[^\w\-']+", "", w.lower())


def block_css(brand: dict) -> str:
    cap, kin, col = brand["caption"], brand["kinetic"], brand["colors"]
    acc = col["accent"]
    ok = col.get("ok", "#2fbf5b")
    return f"""
      .g-badge {{ position: absolute; left: 0; right: 0; display: flex; justify-content: center; align-items: center; gap: 22px; }}
      .g-badge .dot {{ width: 112px; height: 112px; border-radius: 50%; color: #fff; font: 700 70px/112px {cap['font']}; text-align: center; box-shadow: 0 6px 18px rgba(0,0,0,.4); }}
      .g-badge .dot.x {{ background: {acc}; }} .g-badge .dot.check {{ background: {ok}; }}
      .g-lbl {{ font: 700 40px {cap['font']}; letter-spacing: .14em; color: #fff; text-transform: uppercase; text-shadow: 0 2px 4px rgba(0,0,0,.7); white-space: nowrap; }}
      .g-arrow {{ position: absolute; inset: 0; }}
      .g-arrow .g-lbl {{ position: absolute; }}
      .g-arrow svg {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }}
      .g-hl {{ position: absolute; left: 0; right: 0; text-align: center; }}
      .g-hl span {{ position: relative; display: inline-block; font: italic 700 124px/1.1 {kin['font']}; color: #fff; padding: 0 28px; z-index: 0; }}
      .g-hl .bar {{ position: absolute; left: 0; right: 0; top: 22%; bottom: 8%; z-index: -1; transform-origin: 0 50%; transform: scaleX(0); }}
      .g-phonebg {{ position: absolute; inset: 0; background: radial-gradient(circle at 50% 38%, #ffffff 0%, #ebe8e3 70%); }}
      .g-phone {{ visibility: hidden; position: absolute; left: 290px; top: 170px; width: 500px; height: 1000px; border-radius: 66px; background: #0b0b0b; padding: 16px; box-shadow: 0 40px 80px rgba(0,0,0,.28); transform: perspective(1600px) rotateY(-14deg) rotateZ(-4deg); }}
      .g-phone .scr {{ position: relative; width: 100%; height: 100%; border-radius: 52px; overflow: hidden; background: #000; }}
      .g-phone video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
      .g-phone .bar {{ position: absolute; top: 26px; left: 30px; right: 30px; height: 6px; display: flex; gap: 8px; z-index: 3; }}
      .g-phone .bar i {{ flex: 1; background: rgba(255,255,255,.4); border-radius: 3px; overflow: hidden; }}
      .g-phone .bar b {{ display: block; height: 100%; width: 100%; background: #fff; transform-origin: 0 50%; transform: scaleX(0); }}
      .g-phone .tag {{ position: absolute; left: 34px; bottom: 44px; z-index: 3; font: 700 30px {cap['font']}; color: #fff; letter-spacing: .08em; text-shadow: 0 2px 4px rgba(0,0,0,.6); }}
      .g-cta {{ position: absolute; left: 0; right: 0; text-align: center; font-family: {cap['font']}; font-weight: 800; text-transform: uppercase; color: #fff; text-shadow: {cap.get('shadow', 'none')}; line-height: 1.08; }}
      .g-cta .m {{ display: block; overflow: hidden; padding-bottom: 6px; }}
      .g-cta .m > span {{ display: inline-block; white-space: nowrap; }}
      .g-cta .ul {{ display: block; height: 10px; width: 640px; margin: 14px auto 0; background: {acc}; transform-origin: 0 50%; transform: scaleX(0); }}
"""


def render_blocks(graphics: list, ctx: dict) -> dict:
    """ctx: snap(t), resolve(spec)->t, shot_end(t)->end of the shot containing t, body_end,
    link_unit(gid)->(src_rel, t0), target_id(spec)->element id, brand, cap_shadow.
    Returns html (list), js (list), sfx (list of events)."""
    out_html, js, sfx = [], [], []
    snap = ctx["snap"]
    brand = ctx["brand"]
    track = 40
    for n, g in enumerate(graphics):
        typ = g.get("type")
        gid = f"g{n + 1}"
        at = snap(ctx["resolve"](g["effects"][0] if typ == "gag" else g))
        default_dur = {"badge": 1.8, "arrow_label": 1.9, "highlight_word": 1.9, "phone_reels": 1.5}.get(typ)
        dur = float(g.get("dur", default_dur or (ctx["shot_end"](at) - at)))
        if typ == "cta" and "dur" not in g:
            dur = ctx["body_end"] - at
        dur = max(0.2, round(dur - 0.004, 4))
        tr = track + n * 3
        y = g.get("y")

        def place(default, h, alts):
            if y is not None:
                ctx["check_y"](f"{typ} '{g.get('text', '')[:20]}'", at, at + dur, y, h)
                return y
            return ctx["fit_y"](at, at + dur, h, [default] + alts)

        if typ == "badge":
            yy = place(300, 112, [1480, 1560])
            icon = "✓" if g.get("icon") == "check" else "✕"
            cls = "check" if g.get("icon") == "check" else "x"
            out_html.append(f'<div id="{gid}" class="g-badge clip" data-start="{at}" data-duration="{dur}" '
                            f'data-track-index="{tr}" style="top:{yy}px"><div class="dot {cls}">{icon}</div>'
                            f'<div class="g-lbl">{html.escape(g["text"])}</div></div>')
            js.append(f'tl.from("#{gid} .dot", {{scale: 0, rotation: -90, duration: 0.35, ease: "back.out(2)"}}, {at});')
            js.append(f'tl.from("#{gid} .g-lbl", {{x: -30, opacity: 0, duration: 0.3, ease: "power3.out"}}, {round(at + 0.12, 3)});')

        elif typ == "arrow_label":
            pts = g["path"]
            d = "M " + " L ".join(f"{x} {y_}" for x, y_ in pts)
            ex, ey = pts[-1]
            lx, ly = g.get("label", [pts[0][0] - 160, pts[0][1] - 70])
            length = sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
                         for i in range(len(pts) - 1))
            out_html.append(f'<div id="{gid}" class="g-arrow clip" data-start="{at}" data-duration="{dur}" data-track-index="{tr}">'
                            f'<svg><path id="{gid}p" d="{d}" fill="none" stroke="#fff" stroke-width="3"/>'
                            f'<circle id="{gid}d" cx="{ex}" cy="{ey}" r="10" fill="{brand["colors"]["accent"]}"/></svg>'
                            f'<div class="g-lbl" style="left:{lx}px; top:{ly}px">{html.escape(g["text"])}</div></div>')
            ctx["check_y"](f"arrow label '{g['text'][:20]}'", at, at + dur, ly, 50, lx, lx + 40 * len(g["text"]))
            L = int(length) + 10
            js.append(f'tl.fromTo("#{gid}p", {{strokeDasharray: {L}, strokeDashoffset: {L}}}, {{strokeDashoffset: 0, duration: 0.42, ease: "power2.out"}}, {round(at + 0.05, 3)});')
            js.append(f'tl.from("#{gid}d", {{scale: 0, transformOrigin: "50% 50%", duration: 0.25, ease: "back.out(3)"}}, {round(at + 0.4, 3)});')
            js.append(f'tl.from("#{gid} .g-lbl", {{y: 16, opacity: 0, duration: 0.3, ease: "power3.out"}}, {at});')

        elif typ == "highlight_word":
            color = g.get("color", brand["colors"].get("ok", "#2fbf5b"))
            yy = place(320, 140, [1480, 1560])
            out_html.append(f'<div id="{gid}" class="g-hl clip" data-start="{at}" data-duration="{dur}" data-track-index="{tr}" '
                            f'style="top:{yy}px"><span id="{gid}w"><i id="{gid}b" class="bar" style="background:{color}"></i>'
                            f'{html.escape(g["text"])}</span></div>')
            js.append(f'tl.from("#{gid}w", {{yPercent: 50, opacity: 0, duration: 0.3, ease: "power3.out"}}, {at});')
            js.append(f'tl.to("#{gid}b", {{scaleX: 1, duration: 0.35, ease: "power2.inOut"}}, {round(at + 0.25, 3)});')

        elif typ == "phone_reels":
            units = g["units"]
            ins = g.get("in", [None] * len(units))
            seg = round(dur / len(units), 4)
            vids, bars = [], []
            for k, u in enumerate(units):
                rel, t0 = ctx["link_unit"](u)
                s0 = snap(at + k * seg)
                sd = round((at + dur) - s0 if k == len(units) - 1 else seg, 4)
                vids.append(f'<video id="{gid}v{k}" class="clip" src="{rel}" data-start="{s0}" data-duration="{sd}" '
                            f'data-media-start="{ins[k] if ins[k] is not None else t0}" data-track-index="{tr + k}" muted playsinline></video>')
                bars.append(f'<i><b id="{gid}b{k}"></b></i>')
                js.append(f'tl.to("#{gid}b{k}", {{scaleX: 1, duration: {sd}, ease: "none"}}, {s0});')
                if k:
                    js.append(f'tl.from("#{gid}v{k}", {{yPercent: 100, duration: 0.18, ease: "power3.out"}}, {s0});')
            out_html.append(f'<div id="{gid}bg" class="g-phonebg clip" data-start="{at}" data-duration="{dur}" data-track-index="{tr + 10}"></div>')
            out_html.append(f'<div id="{gid}" class="g-phone"><div class="scr">' + "".join(vids) +
                            f'<div class="bar">{"".join(bars)}</div><div class="tag">{html.escape(g.get("tag", "NEW REEL"))}</div></div></div>')
            end = round(at + dur, 4)
            js.append(f'tl.from("#{gid}bg", {{opacity: 0, duration: 0.15, ease: "none"}}, {at});')
            js.append(f'tl.set("#{gid}", {{visibility: "visible"}}, {at});')
            js.append(f'tl.set("#{gid}", {{visibility: "hidden"}}, {end});')
            js.append(f'tl.from("#{gid}", {{y: 900, rotateZ: 6, duration: 0.45, ease: "back.out(1.2)"}}, {at});')
            # captions turn dark on the white cut-away
            js.append(f'tl.set(".cap", {{color: "#111", textShadow: "none"}}, {at});')
            js.append(f'tl.set(".cap", {{color: "#fff", textShadow: "{ctx["cap_shadow"]}"}}, {end});')

        elif typ == "gag":
            tid = ctx["target_id"](g["target"])
            fxs = [e["fx"] for e in g["effects"]]
            for k, e in enumerate(g["effects"]):
                t = snap(ctx["resolve"](e))
                state = " ".join(GAG_FX[f] if i <= k else GAG_ZERO[f] for i, f in enumerate(fxs))
                if k == 0:
                    zero = " ".join(GAG_ZERO[f] for f in fxs)
                    js.append(f'tl.fromTo("#{tid}", {{filter: "{zero}"}}, {{filter: "{state}", duration: 0.25, ease: "power2.out"}}, {t});')
                else:
                    js.append(f'tl.to("#{tid}", {{filter: "{state}", duration: 0.3, ease: "power2.out"}}, {t});')
            continue  # no element of its own

        elif typ == "cta":
            lines = g["lines"]
            longest = max(len(x) for x in lines)
            size = int(min(g.get("size", 78), 940 / (0.74 * longest)))
            yy = place(1420, int(len(lines) * size * 1.12 + 30), [1240, 1520, 300])
            spans = "".join(f'<span class="m"><span id="{gid}l{k}">{html.escape(x)}</span></span>' for k, x in enumerate(lines))
            ul = f'<span id="{gid}u" class="ul"></span>' if g.get("underline", True) else ""
            out_html.append(f'<div id="{gid}" class="g-cta clip" data-start="{at}" data-duration="{dur}" data-track-index="{tr}" '
                            f'style="top:{yy}px; font-size:{size}px">{spans}{ul}</div>')
            for k in range(len(lines)):
                js.append(f'tl.from("#{gid}l{k}", {{yPercent: 110, duration: 0.4, ease: "power3.out"}}, {round(at + 0.28 * k, 3)});')
            if ul:
                js.append(f'tl.to("#{gid}u", {{scaleX: 1, duration: 0.45, ease: "power2.inOut"}}, {round(at + 0.28 * len(lines) + 0.17, 3)});')
        else:
            raise ValueError(f"graphics[{n}]: unknown type '{typ}'")

        role = g.get("sfx", DEFAULT_SFX.get(typ, "none"))
        if role and role != "none":
            sfx.append({"at": at, "role": role, "align": "start", "max_dur": 1.2, "why": f"{typ} '{g.get('text', '')[:20]}'"})
    return {"html": out_html, "js": js, "sfx": sfx}
