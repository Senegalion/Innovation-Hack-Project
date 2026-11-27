import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Equipment, Experiment, Lab, Material, Sample, Space, User, Workstation
from ..deps import current_user, get_db, name_of, require, ser
from ..i18n import get_lang
from ..realtime import hub
from ..services import spatial
from ..services.assets import asset, asset_dict, lab_assets, log
from ..services.documents import store_upload
from ..services.forecast import forecast_material
from ..services.model_import import analyze_model

router = APIRouter(prefix="/api", tags=["labs"])


def get_lab(db: Session, lab_id: str) -> Lab:
    lab = db.get(Lab, lab_id)
    if not lab:
        raise HTTPException(404, "Lab not found")
    return lab


def space_dict(s: Space) -> dict:
    return {**ser(s), "label": s.name}


@router.get("/labs")
def labs(db: Session = Depends(get_db)):
    out = []
    for lab in db.query(Lab):
        eq = db.query(Equipment).filter_by(lab_id=lab.id).all()
        out.append({**ser(lab), "floorplan": None, "alerts": sum(e.status == "alert" for e in eq),
                    "maint": sum(e.status == "maint" for e in eq), "manager": name_of(db, lab.manager_id)})
    return out


@router.get("/labs/{lab_id}")
def lab_detail(lab_id: str, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    lab = get_lab(db, lab_id)
    exps = db.query(Experiment).filter_by(lab_id=lab_id).all()
    spaces = db.query(Space).filter_by(lab_id=lab_id).all()
    return {
        **ser(lab), "floorplan": None, "manager": name_of(db, lab.manager_id),
        "equipment": [asset_dict(db, a) for a in lab_assets(db, lab_id)],
        "workstations": [a.id for a in lab_assets(db, lab_id) if a.__tablename__ == "workstations"],
        "materials": [{**ser(m), "forecast": forecast_material(m, exps, db, lang), "responsible": name_of(db, m.responsible_id)}
                      for m in db.query(Material).filter_by(lab_id=lab_id)],
        "experiments": [{**ser(x), "lead": name_of(db, x.lead_id)} for x in exps],
        "samples": [ser(s) for s in db.query(Sample).filter_by(lab_id=lab_id)],
        "spaces": [space_dict(s) for s in spaces],
        "zones": [space_dict(s) for s in spaces if s.kind == "zone"],
    }


@router.get("/labs/{lab_id}/floorplan")
def get_floorplan(lab_id: str, format: str = "json", db: Session = Depends(get_db),
                  user: User | None = Depends(current_user)):
    lab = get_lab(db, lab_id)
    if format == "svg":
        return Response(spatial.floorplan_svg(db, lab), media_type="image/svg+xml")
    return spatial.floorplan(db, lab, user)


@router.post("/labs/{lab_id}/floorplan/from-model")
async def floorplan_from_model(lab_id: str, file: UploadFile = File(...), up: str = Form("y"),
                               cell: float = Form(spatial.CELL), apply: bool = Form(True),
                               db: Session = Depends(get_db), user: User = Depends(require("leader"))):
    lab = get_lab(db, lab_id)
    data = await file.read()
    try:
        pts = spatial.load_points(data, file.filename or "model.glb", up)
        fp = spatial.occupancy_from_points(pts, cell)
    except Exception as e:
        raise HTTPException(422, f"Could not read 3D model: {e}") from e
    doc = store_upload(db, data, file.filename or "model", file.content_type or "application/octet-stream",
                       None, None, lab_id, "lab", lab_id, user.id)
    doc.status, doc.processor = "processed", "floorplan"
    fp.update({"source": f"document:{doc.id}", "points": int(len(pts))})
    if apply:
        lab.floorplan = fp
        lab.width, lab.depth = max(lab.width, fp["width"]), max(lab.depth, fp["depth"])
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return {**fp, "document_id": doc.id, "applied": apply}


@router.delete("/labs/{lab_id}/floorplan")
async def reset_floorplan(lab_id: str, db: Session = Depends(get_db), _: User = Depends(require("leader"))):
    get_lab(db, lab_id).floorplan = None
    db.commit()
    return {"ok": True}


@router.get("/labs/{lab_id}/export/model.glb")
def export_glb(lab_id: str, db: Session = Depends(get_db)):
    scene = spatial.export_twin_mesh(db, get_lab(db, lab_id))
    return Response(scene.export(file_type="glb"), media_type="model/gltf-binary",
                    headers={"Content-Disposition": f'attachment; filename="{lab_id}.glb"'})


@router.get("/labs/{lab_id}/export/pointcloud.ply")
def export_pointcloud(lab_id: str, points: int = 40000, db: Session = Depends(get_db)):
    pts = spatial.synthetic_scan(db, get_lab(db, lab_id), n=min(max(points, 1000), 200000))
    return Response(spatial.ply_bytes(pts), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{lab_id}-scan.ply"'})


class LabIn(BaseModel):
    code: str
    name: str
    building: str = ""
    width: float = 20
    depth: float = 14
    manager_id: str | None = None
    id: str | None = None


@router.post("/labs")
async def create_lab(body: LabIn, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    lab_id = body.id or "lab-" + re.sub(r"[^a-z0-9]+", "-", body.code.lower()).strip("-")
    if db.get(Lab, lab_id):
        raise HTTPException(409, "Lab id already exists")
    lab = Lab(id=lab_id, code=body.code, name=body.name, building=body.building,
              manager_id=body.manager_id or admin.id, width=body.width, depth=body.depth,
              entrance=[body.width / 2, body.depth - 0.4], points=[])
    db.add(lab)
    log(db, lab_id, admin.id, "lab", lab_id, "created", note=body.name)
    db.commit()
    hub.queue({"type": "labs"})
    await hub.flush()
    return ser(lab)


def unique_asset_id(db: Session, wanted: str, lab: Lab, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", wanted).strip("-").upper() or "OBJ"
    candidate = base
    existing = asset(db, candidate)
    if (existing and existing.lab_id != lab.id) or candidate in taken:
        candidate = f"{lab.code}-{base}".upper()
    n = 2
    while (asset(db, candidate) and asset(db, candidate).lab_id != lab.id) or candidate in taken:
        candidate = f"{lab.code}-{base}-{n}".upper()
        n += 1
    return candidate


@router.post("/labs/{lab_id}/model")
async def upload_model(lab_id: str, file: UploadFile = File(...), manifest: UploadFile | None = File(None),
                       import_assets: bool = Form(True), resize_lab: bool = Form(True),
                       db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    lab = get_lab(db, lab_id)
    data = await file.read()
    items = None
    if manifest is not None:
        try:
            items = json.loads((await manifest.read()).decode("utf-8"))
            items = items.get("objects", items) if isinstance(items, dict) else items
        except Exception as e:
            raise HTTPException(422, f"Invalid manifest: {e}") from e
    try:
        result = analyze_model(data, file.filename or "model.glb", items)
    except Exception as e:
        raise HTTPException(422, f"Could not read 3D model: {e}") from e
    doc = store_upload(db, result["glb"], (file.filename or "model").rsplit(".", 1)[0] + ".glb", "model/gltf-binary",
                       f"3D model — {lab.name}", "model", lab_id, "lab", lab_id, admin.id)
    doc.status, doc.processor = "stored", "model-import"
    if resize_lab:
        lab.width, lab.depth = max(result["width"], 1.0), max(result["depth"], 1.0)
        lab.entrance = [lab.width / 2, lab.depth - 0.4]
    lab.floorplan = {**result["floorplan"], "source": f"document:{doc.id}"}
    lab.glb_url = f"/api/documents/{doc.id}/download"
    nodes, created, updated, taken = {}, [], [], set()
    if import_assets:
        for o in result["objects"]:
            existing = asset(db, o["id"])
            aid = o["id"].upper() if existing and existing.lab_id == lab_id else unique_asset_id(db, o["id"], lab, taken)
            taken.add(aid)
            nodes[o["node"]] = aid
            geom = dict(x=o["x"], z=o["z"], w=o["w"], d=o["d"], h=o["h"])
            a = asset(db, aid)
            if a:
                for k, v in geom.items():
                    setattr(a, k, v)
                updated.append(aid)
                continue
            if o["kind"] == "bench":
                db.add(Workstation(id=aid, lab_id=lab_id, name=o["name"], **geom))
            else:
                db.add(Equipment(id=aid, lab_id=lab_id, name=o["name"], kind=o["kind"],
                                 category=o.get("category") or "Model 3D", storage_class=o.get("storage_class"),
                                 status="ok", **geom))
            created.append(aid)
    lab.model_meta = {"document_id": doc.id, "offset": result["offset"], "size": [lab.width, result["height"], lab.depth],
                      "nodes": nodes, "filename": file.filename}
    log(db, lab_id, admin.id, "lab", lab_id, "model_uploaded",
        data={"document": doc.id, "created": created, "updated": updated})
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return {"lab": ser(lab), "created": created, "updated": updated, "objects": len(result["objects"]),
            "nodes_total": result["nodes_total"], "occupied_ratio": result["floorplan"]["occupied_ratio"]}


@router.delete("/labs/{lab_id}/model")
async def remove_model(lab_id: str, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    lab = get_lab(db, lab_id)
    lab.glb_url, lab.model_meta, lab.floorplan = None, None, None
    log(db, lab_id, admin.id, "lab", lab_id, "model_removed")
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return {"ok": True}
