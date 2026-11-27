from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import Equipment, Experiment, Lab, Material, Sample, Space, User
from ..deps import current_user, get_db, name_of, require, ser
from ..i18n import get_lang
from ..realtime import hub
from ..services import spatial
from ..services.assets import asset_dict, lab_assets
from ..services.documents import store_upload
from ..services.forecast import forecast_material

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
