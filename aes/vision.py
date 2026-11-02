"""Local vision with SigLIP (multilingual), 0 API tokens. Needs the `ml` extra (torch + transformers).

aes vision <name>   tags every b-roll unit (people, garment colour/type, framing, view, extras) and stores
                    an image embedding per unit. Tags become the unit description when no description
                    exists, so `aes describe --pending` has nothing left to send to Haiku (engine "local").
aes match <name> "phrase" ...   ranks b-roll units for each phrase (English, Hindi or Urdu text all work),
                    combining similarity with the quality score. Paste the top picks into plan.json covers.

Model and cache: config whisper/vision -> models live in HF_HOME (set to E:/hf-models by aes.cmd).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .util import info, load_config, path_of, project_dir, read_json, write_json

MODEL_ID = "google/siglip-base-patch16-256-multilingual"

COLOURS = ["black", "white", "pink", "light blue", "dark green", "grey", "beige", "red", "maroon", "navy blue", "brown"]
GARMENTS = ["hoodie", "t-shirt", "jacket", "kurta", "shirt", "dress", "sweatshirt"]
PEOPLE = {"one man": "man", "one woman": "woman", "two men": "two men", "a man and a woman": "man and woman",
          "a group of people": "group"}
# yes/no tags decided by contrast (SigLIP's absolute probabilities are poorly calibrated)
PERSON = ("a person wearing clothes", ["clothes with nobody wearing them", "a fabric close-up"])
NOBODY = {"clothes hanging on a rack": "clothes rack", "a fabric close-up": "fabric close-up",
          "a close-up of a printed logo on clothing": "print close-up"}
PAIRS = {"hood up": ("a person with the hood up over the head", "a person with the hood down"),
         "cap": ("a person wearing a cap", "a person with no hat"),
         "walking": ("a person walking", "a person standing still")}
FRAMING = {"a full-body wide shot": "wide", "a medium shot from the waist up": "medium",
           "a close-up of fabric": "fabric close-up", "a close-up of a printed logo on clothing": "print close-up"}
VIEW = {"facing the camera": "facing camera", "in side profile": "profile", "seen from behind": "back view"}


class Siglip:
    def __init__(self):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.dev == "cuda" else torch.float32
        self.model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=dtype).to(self.dev).eval()
        self.proc = AutoProcessor.from_pretrained(MODEL_ID)
        self.dtype = dtype

    def images(self, imgs: list) -> np.ndarray:
        with self.torch.no_grad():
            x = self.proc(images=imgs, return_tensors="pt").to(self.dev)
            f = self.model.get_image_features(pixel_values=x["pixel_values"].to(self.dtype))
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def texts(self, texts: list[str]) -> np.ndarray:
        with self.torch.no_grad():
            x = self.proc(text=texts, padding="max_length", return_tensors="pt", truncation=True).to(self.dev)
            f = self.model.get_text_features(**x)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def probs(self, img_emb: np.ndarray, txt_emb: np.ndarray) -> np.ndarray:
        scale = self.model.logit_scale.exp().item()
        bias = self.model.logit_bias.item()
        return 1 / (1 + np.exp(-(img_emb @ txt_emb.T * scale + bias)))


def _frame(src: str, t: float):
    import cv2
    from PIL import Image
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, f = cap.read()
    cap.release()
    if not ok:
        return None
    h, w = f.shape[:2]
    s = 512 / max(h, w)
    f = cv2.resize(f, (int(w * s), int(h * s)))
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))


def vision(name: str, force: bool = False) -> None:
    from .project import load_units
    d = project_dir(name)
    pj = read_json(d / "project.json")
    units = [u for u in load_units(pj) if u["kind"] == "broll" and u.get("q", 0) > 0]
    info(f"SigLIP on {len(units)} b-roll units ...")
    sg = Siglip()
    tmpl = "a photo of {}"
    garm = [f"{c} {g}" for c in COLOURS for g in GARMENTS]
    sets = {"people": list(PEOPLE), "garment": garm, "framing": list(FRAMING), "view": list(VIEW)}
    emb_sets = {k: sg.texts([tmpl.format(x) for x in v]) for k, v in sets.items()}
    e_person = sg.texts([tmpl.format(PERSON[0])] + [tmpl.format(x) for x in PERSON[1]])
    e_nobody = sg.texts([tmpl.format(x) for x in NOBODY])
    e_pairs = {k: sg.texts([tmpl.format(a), tmpl.format(b)]) for k, (a, b) in PAIRS.items()}
    by_cache: dict[str, list[dict]] = {}
    for u in units:
        by_cache.setdefault(u["cache"], []).append(u)
    n = 0
    for cache, us in by_cache.items():
        cdir = path_of("cache") / cache
        ef, tf = cdir / "siglip.npz", cdir / "tags.json"
        if ef.exists() and tf.exists() and not force:
            continue
        imgs, keep = [], []
        for u in us:
            im = _frame(u["source"], (u["t0"] + u["t1"]) / 2)
            if im is not None:
                imgs.append(im)
                keep.append(u)
        if not imgs:
            continue
        emb = sg.images(imgs)
        tags = {}
        for u, e in zip(keep, emb):
            pick = {k: sets[k][int(np.argmax(e @ emb_sets[k].T))] for k in sets}
            ps = e @ e_person.T
            if ps[0] < max(ps[1:]):
                parts = [list(NOBODY.values())[int(np.argmax(e @ e_nobody.T))], pick["garment"].split(" ", 1)[0] + " garments"]
            else:
                parts = [PEOPLE[pick["people"]], pick["garment"], FRAMING[pick["framing"]], VIEW[pick["view"]]]
                parts += [k for k, pe in e_pairs.items() if float(e @ pe[0]) > float(e @ pe[1])]
            tags[u["id"]] = "auto: " + ", ".join(dict.fromkeys(parts))
        np.savez_compressed(ef, ids=np.array([u["id"] for u in keep]), emb=emb.astype(np.float16))
        tf.write_text(json.dumps(tags, ensure_ascii=False, indent=0), encoding="utf-8")
        n += len(keep)
    info(f"Tagged and embedded {n} units (cached per clip). Run: aes candidates {name}")


def match(name: str, phrases: list[str], top: int = 5) -> None:
    from .project import load_units
    d = project_dir(name)
    pj = read_json(d / "project.json")
    units = {u["gid"]: u for u in load_units(pj) if u["kind"] == "broll"}
    ids, embs = [], []
    for c in pj["clips"]:
        ef = path_of("cache") / c["cache"] / "siglip.npz"
        if ef.exists():
            z = np.load(ef)
            for uid, e in zip(z["ids"], z["emb"]):
                gid = f"{c['alias']}-{uid}"
                if gid in units:
                    ids.append(gid)
                    embs.append(e.astype(np.float32))
    if not ids:
        info(f"No embeddings yet. Run: aes vision {name}")
        return
    E = np.stack(embs)
    sg = Siglip()
    T = sg.texts([f"a photo of {p}" for p in phrases])
    sims = T @ E.T
    out = {}
    for i, ph in enumerate(phrases):
        s = sims[i]
        z = (s - s.mean()) / (s.std() + 1e-6)
        score = z + np.array([units[g].get("q", 0) for g in ids]) / 100.0
        order = np.argsort(-score)
        seen, rows = set(), []
        for j in order:
            g = ids[j]
            if g.split("-")[0] in seen:  # one unit per clip, so the list shows variety
                continue
            seen.add(g.split("-")[0])
            u = units[g]
            rows.append(f"  {g}  q{u.get('q', 0)}  sim {s[j]:.3f}  {(u.get('desc') or '')[:70]}")
            if len(rows) >= top:
                break
        out[ph] = rows
        info(f'"{ph}"\n' + "\n".join(rows))
    write_json(d / "matches.json", out)
