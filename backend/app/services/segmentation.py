import json
import urllib.request
import uuid

import numpy as np

from ..config import SEGMENTATION_URL

EXTERNAL_METHODS = {"sam3d": "sam-3d-objects", "openpcseg": "OpenPCSeg"}


class SegmentationUnavailable(Exception):
    pass


def classify(w: float, d: float, h: float, base: float, fill: float = 1.0) -> str:
    footprint = w * d
    if h > 1.8 and ((max(w, d) > 2.5 and min(w, d) <= 0.45) or (footprint > 6 and fill < 0.25)):
        return "wall"
    if base > 0.5:
        return "instrument"
    if 0.7 <= h <= 1.1 and max(w, d) >= 1.5:
        return "bench"
    if h >= 1.5 and footprint <= 4:
        return "cabinet_or_freezer" if max(w, d) <= 1.6 else "fume_hood"
    if h >= 1.5:
        return "fume_hood"
    return "instrument"


def estimate_floor(y: np.ndarray) -> float:
    low = float(np.percentile(y, 1))
    band = y[(y >= low) & (y <= low + 0.3)]
    if not len(band):
        return low
    hist, edges = np.histogram(band, bins=max(1, int(0.3 / 0.02)))
    dense = np.nonzero(hist >= 0.5 * hist.max())[0]
    return float((edges[dense[-1]] + edges[dense[-1] + 1]) / 2)


def geometric_instances(pts: np.ndarray, cell: float = 0.2, min_cells: int = 3, step: float = 0.3) -> dict:
    floor = estimate_floor(pts[:, 1])
    rel = pts[:, 1] - floor
    sel = pts[(rel > 0.1) & (rel < 3.0)]
    if not len(sel):
        return {"floor_y": floor, "instances": []}
    x0, z0 = float(pts[:, 0].min()), float(pts[:, 2].min())
    cols = int(np.ceil((pts[:, 0].max() - x0) / cell)) + 1
    rows = int(np.ceil((pts[:, 2].max() - z0) / cell)) + 1
    top = np.full((rows, cols), -1.0)
    c = np.clip(((sel[:, 0] - x0) / cell).astype(int), 0, cols - 1)
    r = np.clip(((sel[:, 2] - z0) / cell).astype(int), 0, rows - 1)
    np.maximum.at(top, (r, c), sel[:, 1] - floor)
    counts = np.zeros((rows, cols), dtype=int)
    np.add.at(counts, (r, c), 1)
    labels = np.zeros((rows, cols), dtype=int)
    current = 0
    for sr, sc in zip(*np.nonzero(top > 0)):
        if labels[sr, sc]:
            continue
        current += 1
        stack = [(sr, sc)]
        labels[sr, sc] = current
        while stack:
            cr, cc = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nr, nc = cr + dr, cc + dc
                if (0 <= nr < rows and 0 <= nc < cols and not labels[nr, nc] and top[nr, nc] > 0
                        and abs(top[nr, nc] - top[cr, cc]) < step):
                    labels[nr, nc] = current
                    stack.append((nr, nc))
    instances = []
    for k in range(1, current + 1):
        mask = labels == k
        n = int(mask.sum())
        if n < min_cells:
            continue
        rr, cc = np.nonzero(mask)
        xmin, xmax = x0 + cc.min() * cell, x0 + (cc.max() + 1) * cell
        zmin, zmax = z0 + rr.min() * cell, z0 + (rr.max() + 1) * cell
        heights = top[mask]
        h = float(np.percentile(heights, 90))
        ring = np.zeros_like(mask)
        ring[max(rr.min() - 1, 0):rr.max() + 2, max(cc.min() - 1, 0):cc.max() + 2] = True
        ring &= ~mask & (top > 0)
        base = float(np.median(top[ring])) if ring.any() and np.median(top[ring]) < h - step else 0.0
        w, d = xmax - xmin, zmax - zmin
        instances.append({
            "id": f"inst-{uuid.uuid4().hex[:6]}", "label": classify(w, d, h - base, base, n * cell * cell / max(w * d, 1e-9)),
            "x": round((xmin + xmax) / 2, 2), "z": round((zmin + zmax) / 2, 2), "w": round(w, 2),
            "d": round(d, 2), "h": round(h - base, 2), "base": round(base, 2), "cells": n,
            "points": int(counts[mask].sum()), "confidence": round(min(0.95, 0.4 + n / 400), 2),
        })
    instances.sort(key=lambda i: -i["cells"])
    return {"floor_y": floor, "instances": instances}


def external_instances(method: str, data: bytes, filename: str) -> dict:
    if not SEGMENTATION_URL:
        raise SegmentationUnavailable(f"{EXTERNAL_METHODS[method]} service not configured (SEGMENTATION_URL)")
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{SEGMENTATION_URL.rstrip('/')}/segment?method={method}", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except Exception as e:
        raise SegmentationUnavailable(f"{EXTERNAL_METHODS[method]} service error: {e}") from e


def iou_2d(a: dict, b) -> float:
    ax0, ax1, az0, az1 = a["x"] - a["w"] / 2, a["x"] + a["w"] / 2, a["z"] - a["d"] / 2, a["z"] + a["d"] / 2
    bx0, bx1, bz0, bz1 = b.x - b.w / 2, b.x + b.w / 2, b.z - b.d / 2, b.z + b.d / 2
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iz = max(0.0, min(az1, bz1) - max(az0, bz0))
    inter = ix * iz
    union = a["w"] * a["d"] + b.w * b.d - inter
    return inter / union if union > 0 else 0.0


def match_assets(instances: list[dict], assets: list) -> list[dict]:
    for inst in instances:
        best, score = None, 0.0
        for a in assets:
            s = iou_2d(inst, a)
            if s > score:
                best, score = a, s
        inst["matched_asset"] = best.id if best and score >= 0.3 else None
        inst["match_iou"] = round(score, 2)
    return instances
