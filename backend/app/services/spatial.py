import heapq
import io
import itertools
import math

import numpy as np
import trimesh
from sqlalchemy.orm import Session

from ..db import Lab, Space, User
from ..i18n import DEFAULT_LANG, tr
from .assets import lab_assets, locate

CELL = 0.5
HAZARD_COST = 4.0
WALK_SPEED_MPS = 1.0


class Grid:
    def __init__(self, lab: Lab, cell: float = CELL):
        self.cell = cell
        self.cols = max(1, int(round(lab.width / cell)))
        self.rows = max(1, int(round(lab.depth / cell)))
        self.blocked = np.zeros((self.rows, self.cols), dtype=bool)
        self.cost = np.ones((self.rows, self.cols), dtype=float)

    def cell_of(self, x: float, z: float) -> tuple[int, int]:
        return (min(self.rows - 1, max(0, int(z / self.cell))), min(self.cols - 1, max(0, int(x / self.cell))))

    def center(self, r: int, c: int) -> list[float]:
        return [round((c + 0.5) * self.cell, 3), round((r + 0.5) * self.cell, 3)]

    def rect_mask(self, x: float, z: float, w: float, d: float, pad: float = 0.0) -> np.ndarray:
        cx = (np.arange(self.cols) + 0.5) * self.cell
        cz = (np.arange(self.rows) + 0.5) * self.cell
        mx = (cx >= x - w / 2 - pad) & (cx <= x + w / 2 + pad)
        mz = (cz >= z - d / 2 - pad) & (cz <= z + d / 2 + pad)
        return np.outer(mz, mx)

    def to_rows(self) -> list[str]:
        return ["".join("1" if v else "0" for v in row) for row in self.blocked]


def can_enter(space: Space, user: User | None) -> bool:
    if space.closed:
        return False
    if not space.restricted:
        return True
    return bool(user and (user.role in (space.access_roles or []) or user.access == "admin"))


def build_grid(db: Session, lab: Lab, user: User | None = None, pad: float = 0.25) -> tuple[Grid, list[dict]]:
    g = Grid(lab)
    for a in lab_assets(db, lab.id):
        g.blocked |= g.rect_mask(a.x, a.z, a.w, a.d, pad)
    fp = lab.floorplan or {}
    if fp.get("occupancy") and fp.get("cell"):
        occ = np.array([[ch == "1" for ch in row] for row in fp["occupancy"]], dtype=bool)
        scale = fp["cell"]
        for r, c in zip(*np.nonzero(occ)):
            x, z = (c + 0.5) * scale + fp.get("origin", [0, 0])[0], (r + 0.5) * scale + fp.get("origin", [0, 0])[1]
            if 0 <= x < lab.width and 0 <= z < lab.depth:
                gr, gc = g.cell_of(x, z)
                g.blocked[gr, gc] = True
    avoided = []
    for s in db.query(Space).filter_by(lab_id=lab.id):
        m = g.rect_mask(s.x, s.z, s.w, s.d)
        if not can_enter(s, user):
            g.blocked |= m
            avoided.append({"id": s.id, "name": s.name, "reason": "closed" if s.closed else "restricted",
                            "x": s.x, "z": s.z, "w": s.w, "d": s.d})
        elif s.hazard:
            g.cost[m] = np.maximum(g.cost[m], HAZARD_COST)
    return g, avoided


def nearest_free(g: Grid, start: tuple[int, int]) -> tuple[int, int] | None:
    seen, q = {start}, [start]
    i = 0
    while i < len(q):
        r, c = q[i]
        i += 1
        if not g.blocked[r, c]:
            return r, c
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (r + dr, c + dc)
            if 0 <= n[0] < g.rows and 0 <= n[1] < g.cols and n not in seen:
                seen.add(n)
                q.append(n)
    return None


def astar(g: Grid, a: tuple[int, int], b: tuple[int, int]) -> tuple[list[tuple[int, int]], float, float]:
    def h(p):
        return math.hypot(p[0] - b[0], p[1] - b[1])

    openq = [(h(a), 0.0, a)]
    came: dict = {}
    gcost = {a: 0.0}
    dist = {a: 0.0}
    while openq:
        _, cost, cur = heapq.heappop(openq)
        if cur == b:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1], gcost[b], dist[b]
        if cost > gcost.get(cur, math.inf):
            continue
        for dr, dc in itertools.product((-1, 0, 1), repeat=2):
            if not dr and not dc:
                continue
            n = (cur[0] + dr, cur[1] + dc)
            if not (0 <= n[0] < g.rows and 0 <= n[1] < g.cols) or g.blocked[n]:
                continue
            if dr and dc and (g.blocked[cur[0] + dr, cur[1]] or g.blocked[cur[0], cur[1] + dc]):
                continue
            step = math.hypot(dr, dc)
            ng = cost + step * g.cost[n]
            if ng < gcost.get(n, math.inf):
                gcost[n], came[n], dist[n] = ng, cur, dist[cur] + step
                heapq.heappush(openq, (ng + h(n), ng, n))
    return [], math.inf, math.inf


def plan_route(db: Session, lab_id: str, stop_ids: list[str], start: list[float] | None = None,
               user: User | None = None, task_minutes: dict[str, float] | None = None,
               lang: str = DEFAULT_LANG) -> dict:
    lab = db.get(Lab, lab_id)
    g, avoided = build_grid(db, lab, user)
    sx, sz = start or lab.entrance
    origin = nearest_free(g, g.cell_of(sx, sz))
    stops, unreachable, nodes = [], [], [origin]
    for sid in dict.fromkeys(stop_ids):
        loc = locate(db, sid)
        if not loc or loc["lab_id"] != lab_id:
            unreachable.append({"id": sid, "reason": tr(lang, "route.notInLab")})
            continue
        inside = next((sp for sp in avoided if abs(loc["x"] - sp["x"]) <= sp["w"] / 2
                       and abs(loc["z"] - sp["z"]) <= sp["d"] / 2), None)
        if inside:
            unreachable.append({"id": sid, "reason": tr(lang, "route.inside", kind=tr(lang, f"route.kind.{inside['reason']}"),
                                                        name=inside["name"])})
            continue
        cell = nearest_free(g, g.cell_of(loc["x"], loc["z"]))
        if cell is None:
            unreachable.append({"id": sid, "reason": tr(lang, "route.noCell")})
            continue
        stops.append({"id": sid, "asset_id": loc["asset_id"], "name": loc["name"]})
        nodes.append(cell)

    cache: dict = {}

    def seg(i, j):
        if (i, j) not in cache:
            cache[(i, j)] = astar(g, nodes[i], nodes[j])
        return cache[(i, j)]

    reachable = [i for i in range(1, len(nodes)) if math.isfinite(seg(0, i)[1])]
    for i in range(1, len(nodes)):
        if i not in reachable:
            unreachable.append({"id": stops[i - 1]["id"], "reason": tr(lang, "route.blocked")})
    if len(reachable) <= 7:
        best = min(itertools.permutations(reachable),
                   key=lambda p: sum(seg(a, b)[1] for a, b in zip((0,) + p, p)), default=())
    else:
        best, cur, left = [], 0, set(reachable)
        while left:
            nxt = min(left, key=lambda j: seg(cur, j)[1])
            best.append(nxt)
            left.remove(nxt)
            cur = nxt
    order = list(best)
    points, total_dist, clock, legs = [], 0.0, 0.0, []
    task_minutes = task_minutes or {}
    for a, b in zip([0] + order, order):
        path, _, d = seg(a, b)
        walk_m = d * g.cell
        total_dist += walk_m
        clock += walk_m / WALK_SPEED_MPS / 60
        stop = stops[b - 1]
        work = float(task_minutes.get(stop["id"], 0))
        legs.append({**stop, "walk_m": round(walk_m, 1), "arrive_min": round(clock, 1), "work_min": work})
        clock += work
        points += [g.center(r, c) for r, c in (path if not points else path[1:])]
    return {
        "order": [s["asset_id"] for s in legs],
        "stops": legs,
        "points": points,
        "distance_m": round(total_dist, 1),
        "walk_minutes": round(total_dist / WALK_SPEED_MPS / 60, 1),
        "minutes": round(clock, 1),
        "avoided_spaces": avoided,
        "unreachable": unreachable,
    }


def floorplan(db: Session, lab: Lab, user: User | None = None) -> dict:
    g, avoided = build_grid(db, lab, user, pad=0.0)
    return {"lab_id": lab.id, "cell": g.cell, "cols": g.cols, "rows": g.rows, "width": lab.width,
            "depth": lab.depth, "occupancy": g.to_rows(), "avoided_spaces": avoided,
            "source": (lab.floorplan or {}).get("source", "assets")}


def floorplan_svg(db: Session, lab: Lab) -> str:
    fp = floorplan(db, lab)
    s = 20
    w, h = fp["cols"] * s, fp["rows"] * s
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
             f'<rect width="{w}" height="{h}" fill="#0b0f12"/>']
    for r, row in enumerate(fp["occupancy"]):
        for c, ch in enumerate(row):
            if ch == "1":
                parts.append(f'<rect x="{c * s}" y="{r * s}" width="{s}" height="{s}" fill="#9aa6ac"/>')
    for sp in db.query(Space).filter_by(lab_id=lab.id):
        x0, z0 = (sp.x - sp.w / 2) / fp["cell"] * s, (sp.z - sp.d / 2) / fp["cell"] * s
        parts.append(f'<rect x="{x0}" y="{z0}" width="{sp.w / fp["cell"] * s}" height="{sp.d / fp["cell"] * s}" '
                     f'fill="none" stroke="#3cd0c0" stroke-dasharray="6 4"/>')
    for a in lab_assets(db, lab.id):
        parts.append(f'<text x="{a.x / fp["cell"] * s}" y="{a.z / fp["cell"] * s}" fill="#f4f7f8" font-size="11" '
                     f'text-anchor="middle" font-family="monospace">{a.id}</text>')
    parts.append("</svg>")
    return "".join(parts)


def load_points(data: bytes, filename: str, up: str = "y", samples: int = 60000) -> np.ndarray:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ("xyz", "txt", "csv"):
        pts = np.loadtxt(io.BytesIO(data), delimiter="," if ext == "csv" else None, usecols=(0, 1, 2))
    else:
        loaded = trimesh.load(io.BytesIO(data), file_type=ext, force=None)
        if isinstance(loaded, trimesh.Scene):
            loaded = loaded.to_geometry() if hasattr(loaded, "to_geometry") else loaded.dump(concatenate=True)
        if isinstance(loaded, trimesh.PointCloud):
            pts = np.asarray(loaded.vertices)
        elif isinstance(loaded, trimesh.Trimesh) and len(loaded.faces):
            pts, _ = trimesh.sample.sample_surface(loaded, samples) if loaded.area > 0 else (loaded.vertices, None)
            pts = np.vstack([np.asarray(pts), np.asarray(loaded.vertices)])
        else:
            pts = np.asarray(loaded.vertices)
    pts = np.asarray(pts, dtype=float)
    if up == "z":
        pts = pts[:, [0, 2, 1]]
    return pts


def occupancy_from_points(pts: np.ndarray, cell: float = CELL, band: tuple[float, float] = (0.15, 2.0),
                          min_hits: int = 3) -> dict:
    from .segmentation import estimate_floor

    floor = estimate_floor(pts[:, 1])
    xs, zs = pts[:, 0], pts[:, 2]
    x0, z0 = float(xs.min()), float(zs.min())
    width, depth = float(xs.max() - x0), float(zs.max() - z0)
    cols, rows = max(1, int(math.ceil(width / cell))), max(1, int(math.ceil(depth / cell)))
    rel = pts[:, 1] - floor
    sel = pts[(rel > band[0]) & (rel < band[1])]
    hits = np.zeros((rows, cols), dtype=int)
    if len(sel):
        c = np.clip(((sel[:, 0] - x0) / cell).astype(int), 0, cols - 1)
        r = np.clip(((sel[:, 2] - z0) / cell).astype(int), 0, rows - 1)
        np.add.at(hits, (r, c), 1)
    occ = hits >= min_hits
    return {"cell": cell, "origin": [0, 0], "world_origin": [x0, z0], "floor_y": floor, "cols": cols, "rows": rows,
            "width": round(width, 2), "depth": round(depth, 2),
            "occupancy": ["".join("1" if v else "0" for v in row) for row in occ],
            "occupied_ratio": round(float(occ.mean()), 3)}


def export_twin_mesh(db: Session, lab: Lab) -> trimesh.Scene:
    scene = trimesh.Scene()
    floor = trimesh.Trimesh(vertices=[[0, 0, 0], [lab.width, 0, 0], [lab.width, 0, lab.depth], [0, 0, lab.depth]],
                            faces=[[0, 2, 1], [0, 3, 2]])
    scene.add_geometry(floor, node_name="floor")
    for name, ext, pos in [("wall_back", [lab.width, 2.8, 0.1], [lab.width / 2, 1.4, -0.05]),
                           ("wall_left", [0.1, 2.8, lab.depth], [-0.05, 1.4, lab.depth / 2])]:
        wall = trimesh.creation.box(extents=ext)
        wall.apply_translation(pos)
        scene.add_geometry(wall, node_name=name)
    benches = {a.id: a for a in lab_assets(db, lab.id) if a.__tablename__ == "workstations"}
    for a in lab_assets(db, lab.id):
        base = 0.0
        if a.__tablename__ == "machines":
            for b in benches.values():
                if abs(b.x - a.x) < b.w / 2 and abs(b.z - a.z) < b.d / 2:
                    base = b.h
        box = trimesh.creation.box(extents=[a.w, a.h, a.d])
        box.apply_translation([a.x, base + a.h / 2, a.z])
        scene.add_geometry(box, node_name=a.id)
    return scene


def synthetic_scan(db: Session, lab: Lab, n: int = 80000, noise: float = 0.01) -> np.ndarray:
    mesh = export_twin_mesh(db, lab)
    combined = mesh.to_geometry() if hasattr(mesh, "to_geometry") else mesh.dump(concatenate=True)
    pts, _ = trimesh.sample.sample_surface(combined, n, seed=7)
    rng = np.random.default_rng(7)
    return np.asarray(pts) + rng.normal(0, noise, size=(len(pts), 3))


def ply_bytes(pts: np.ndarray) -> bytes:
    return trimesh.PointCloud(pts).export(file_type="ply")
