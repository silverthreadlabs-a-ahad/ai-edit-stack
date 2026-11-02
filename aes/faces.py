"""Face tracks with OpenCV YuNet (tools/face_detection_yunet_2023mar.onnx), sampled at 2 fps.

cache/<clip>/faces.json = {"fps": 2, "t": [...], "boxes": [[[x0, y0, x1, y1, score], ...], ...]}
(boxes normalized 0-1 to the source frame). Computed once per clip, 0 tokens. The build uses it to keep
captions and graphics off faces for the whole time they are on screen, not just one sampled frame.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from .util import ROOT, info

MODEL = ROOT / "tools" / "face_detection_yunet_2023mar.onnx"
SAMPLE_FPS = 2
SAMPLE_W = 360


def face_track(src: Path, cdir: Path, duration: float, width: int, height: int, force: bool = False) -> dict:
    out = cdir / "faces.json"
    if out.exists() and not force:
        return json.loads(out.read_text(encoding="utf-8"))
    import cv2
    if not MODEL.exists():
        info("  YuNet model missing (tools/face_detection_yunet_2023mar.onnx): face tracks skipped")
        return {"fps": SAMPLE_FPS, "t": [], "boxes": []}
    w = SAMPLE_W
    h = int(round(SAMPLE_W * height / width / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-i", str(src), "-vf", f"fps={SAMPLE_FPS},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    frames = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3) if n else []
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), score_threshold=0.6, nms_threshold=0.3, top_k=20)
    ts, boxes = [], []
    for i, f in enumerate(frames):
        _, faces = det.detect(np.ascontiguousarray(f))
        bs = []
        if faces is not None:
            for x, y, bw, bh, *rest in faces:
                x, y, bw, bh = float(x), float(y), float(bw), float(bh)
                if bh / h < 0.025:  # ignore tiny background faces
                    continue
                # YuNet boxes stop at the brows; extend up for hair/hijab and a little down for the chin
                y0 = max(0.0, (y - 0.25 * bh) / h)
                y1 = min(1.0, (y + 1.1 * bh) / h)
                bs.append([round(max(0.0, x / w), 4), round(y0, 4), round(min(1.0, (x + bw) / w), 4),
                           round(y1, 4), round(float(rest[-1]), 3)])
        ts.append(round(i / SAMPLE_FPS, 3))
        boxes.append(bs)
    data = {"fps": SAMPLE_FPS, "t": ts, "boxes": boxes}
    out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data


def boxes_between(track: dict, t0: float, t1: float) -> list[list[float]]:
    """All face boxes seen in the source window [t0, t1] (normalized)."""
    out = []
    for t, bs in zip(track.get("t", []), track.get("boxes", [])):
        if t0 - 0.25 <= t <= t1 + 0.25:
            out += [b[:4] for b in bs]
    return out
