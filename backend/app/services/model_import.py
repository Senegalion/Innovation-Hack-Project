import io
import re

import numpy as np
import trimesh

from .segmentation import classify
from .spatial import occupancy_from_points

STRUCTURAL = re.compile(r"^(floor|wall|ceiling|room|ground|plane|podloga|podłoga|sciana|ściana|sufit|pokoj|pokój)",
                        re.I)
KIND_FROM_LABEL = {"bench": "bench", "instrument": "instrument", "cabinet_or_freezer": "storage",
                   "fume_hood": "hood"}


def base_name(name: str) -> str:
    return re.sub(r"([._]\d+)+$", "", name or "").strip()


def load_scene(data: bytes, filename: str) -> trimesh.Scene:
    ext = filename.rsplit(".", 1)[-1].lower()
    loaded = trimesh.load(io.BytesIO(data), file_type=ext, force="scene")
    if not isinstance(loaded, trimesh.Scene):
        loaded = trimesh.Scene(loaded)
    if not loaded.geometry:
        raise ValueError("Model contains no geometry")
    return loaded


def top_object(scene: trimesh.Scene, node: str) -> str:
    parents = scene.graph.transforms.parents
    base = scene.graph.base_frame
    current = node
    while parents.get(current) not in (None, base):
        current = parents[current]
    return current


def node_boxes(scene: trimesh.Scene) -> dict[str, np.ndarray]:
    boxes: dict[str, np.ndarray] = {}
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        geom = scene.geometry[geom_name]
        corners = trimesh.bounds.corners(geom.bounds)
        pts = trimesh.transform_points(corners, transform)
        key = top_object(scene, node)
        box = np.array([pts.min(axis=0), pts.max(axis=0)])
        if key in boxes:
            box = np.array([np.minimum(boxes[key][0], box[0]), np.maximum(boxes[key][1], box[1])])
        boxes[key] = box
    return boxes


def analyze_model(data: bytes, filename: str, manifest: list[dict] | None = None) -> dict:
    scene = load_scene(data, filename)
    bmin, bmax = scene.bounds
    width, depth = float(bmax[0] - bmin[0]), float(bmax[2] - bmin[2])
    floor_y = float(bmin[1])
    by_name = {str(m.get("node") or m.get("id")): m for m in (manifest or []) if m.get("node") or m.get("id")}
    objects = []
    for node, (lo, hi) in node_boxes(scene).items():
        name = base_name(node) or node
        extra = by_name.get(node) or by_name.get(name) or {}
        w, h, d = float(hi[0] - lo[0]), float(hi[1] - lo[1]), float(hi[2] - lo[2])
        if extra.get("skip") or (not extra and STRUCTURAL.match(name)):
            continue
        if not extra and (w * d > 0.4 * width * depth or (max(w, d) > 0.8 * max(width, depth) and min(w, d) < 0.5)):
            continue
        if w < 0.05 or d < 0.05:
            continue
        base = float(lo[1]) - floor_y
        label = classify(w, d, h, base)
        if label == "wall" and not extra:
            continue
        objects.append({
            "node": node, "id": extra.get("id") or name, "name": extra.get("name") or name,
            "kind": extra.get("kind") or KIND_FROM_LABEL.get(label, "instrument"),
            "category": extra.get("category"), "storage_class": extra.get("storage_class"),
            "x": round((lo[0] + hi[0]) / 2 - bmin[0], 3), "z": round((lo[2] + hi[2]) / 2 - bmin[2], 3),
            "w": round(w, 3), "d": round(d, 3), "h": round(h, 3), "base": round(base, 3),
        })
    combined = scene.to_geometry() if hasattr(scene, "to_geometry") else scene.dump(concatenate=True)
    if isinstance(combined, trimesh.Trimesh) and len(combined.faces) and combined.area > 0:
        pts, _ = trimesh.sample.sample_surface(combined, 60000, seed=7)
    else:
        pts = np.asarray(combined.vertices)
    pts = np.asarray(pts, dtype=float) - np.array([bmin[0], 0, bmin[2]])
    floorplan = occupancy_from_points(pts)
    floorplan["world_origin"] = [0, 0]
    glb = data if filename.lower().endswith((".glb", ".gltf")) else scene.export(file_type="glb")
    return {
        "width": round(width, 3), "depth": round(depth, 3), "height": round(float(bmax[1] - bmin[1]), 3),
        "offset": [float(bmin[0]), floor_y, float(bmin[2])], "objects": objects, "floorplan": floorplan,
        "glb": glb, "nodes_total": len(scene.graph.nodes_geometry),
    }
