from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Document, Equipment, Lab, Quest, Reconstruction, SessionLocal, User, Workstation
from ..deps import current_user, get_db, require, ser
from ..i18n import DEFAULT_LANG, get_lang, tr
from ..realtime import hub
from ..services import segmentation, spatial
from ..services.assets import lab_assets, log
from ..services.assistant import ask_assistant
from ..services.documents import store_upload
from ..services.storage import storage

router = APIRouter(prefix="/api", tags=["spatial"])


class RouteIn(BaseModel):
    lab_id: str
    stops: list[str] = []
    quest_ids: list[int] = []
    start: list[float] | None = None
    user_id: str | None = None


@router.post("/route")
def route(body: RouteIn, db: Session = Depends(get_db), user: User | None = Depends(current_user),
          lang: str = Depends(get_lang)):
    if not db.get(Lab, body.lab_id):
        raise HTTPException(404, "Lab not found")
    user = user or (db.get(User, body.user_id) if body.user_id else None)
    stops, minutes = list(body.stops), {}
    for q in db.query(Quest).filter(Quest.id.in_(body.quest_ids or [-1])):
        if q.target_id:
            stops.append(q.target_id)
            minutes[q.target_id] = minutes.get(q.target_id, 0) + q.minutes
    return spatial.plan_route(db, body.lab_id, stops, body.start, user, minutes, lang)


class AskIn(BaseModel):
    lab_id: str
    question: str


@router.post("/assistant")
def assistant(body: AskIn, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    return ask_assistant(db, body.lab_id, body.question, lang)


def run_reconstruction(rec_id: int):
    db = SessionLocal()
    try:
        rec = db.get(Reconstruction, rec_id)
        doc = db.get(Document, rec.document_id)
        rec.status = "running"
        db.commit()
        data = storage().get(doc.storage_key)
        notes = []
        method = rec.method
        result = None
        if method in segmentation.EXTERNAL_METHODS:
            try:
                result = segmentation.external_instances(method, data, doc.filename)
            except segmentation.SegmentationUnavailable as e:
                notes.append(tr(DEFAULT_LANG, "seg.unavailable", name=segmentation.EXTERNAL_METHODS[method]))
                notes.append(str(e))
                method = "geometric"
        pts = spatial.load_points(data, doc.filename, rec.up_axis)
        if result is None:
            result = segmentation.geometric_instances(pts)
        instances = segmentation.match_assets(result.get("instances", []), lab_assets(db, rec.lab_id))
        rec.result = {
            "method": method, "notes": notes, "points": int(len(pts)), "instances": instances,
            "matched": sum(1 for i in instances if i["matched_asset"]),
            "unmatched": sum(1 for i in instances if not i["matched_asset"] and i["label"] != "wall"),
            "floorplan": spatial.occupancy_from_points(pts),
        }
        rec.status = "done"
    except Exception as e:
        rec.status, rec.error = "failed", str(e)
    db.commit()
    db.close()


@router.post("/labs/{lab_id}/reconstructions")
async def create_reconstruction(lab_id: str, background: BackgroundTasks, file: UploadFile | None = File(None),
                                document_id: int | None = Form(None), method: str = Form("geometric"),
                                up: str = Form("y"), db: Session = Depends(get_db),
                                user: User = Depends(require("leader"))):
    if not db.get(Lab, lab_id):
        raise HTTPException(404, "Lab not found")
    if method not in ("geometric", *segmentation.EXTERNAL_METHODS):
        raise HTTPException(422, f"Unknown method {method}")
    if file is not None:
        doc = store_upload(db, await file.read(), file.filename or "scan.ply",
                           file.content_type or "application/octet-stream", None, None, lab_id, "lab", lab_id, user.id)
    elif document_id:
        doc = db.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")
    else:
        raise HTTPException(422, "Provide a file or document_id")
    rec = Reconstruction(lab_id=lab_id, document_id=doc.id, method=method, up_axis=up, created_by=user.id)
    db.add(rec)
    db.commit()
    background.add_task(run_reconstruction, rec.id)
    return ser(rec)


@router.get("/labs/{lab_id}/reconstructions")
def list_reconstructions(lab_id: str, db: Session = Depends(get_db)):
    rows = db.query(Reconstruction).filter_by(lab_id=lab_id).order_by(Reconstruction.at.desc()).all()
    return [{**ser(r), "result": {k: v for k, v in (r.result or {}).items() if k != "floorplan"}} for r in rows]


@router.get("/reconstructions/{rec_id}")
def get_reconstruction(rec_id: int, db: Session = Depends(get_db)):
    rec = db.get(Reconstruction, rec_id)
    if not rec:
        raise HTTPException(404)
    return ser(rec)


class AcceptInstance(BaseModel):
    instance_id: str
    asset_id: str
    name: str
    kind: str = "instrument"
    category: str = "Unassigned"


@router.post("/reconstructions/{rec_id}/accept")
async def accept_instance(rec_id: int, body: AcceptInstance, db: Session = Depends(get_db),
                          user: User = Depends(require("admin"))):
    rec = db.get(Reconstruction, rec_id)
    inst = next((i for i in (rec.result or {}).get("instances", []) if i["id"] == body.instance_id), None) if rec else None
    if not inst:
        raise HTTPException(404, "Instance not found")
    if db.get(Equipment, body.asset_id) or db.get(Workstation, body.asset_id):
        raise HTTPException(409, "Asset id already exists")
    geom = dict(x=inst["x"], z=inst["z"], w=inst["w"], d=inst["d"], h=inst["h"])
    if body.kind == "bench":
        a = Workstation(id=body.asset_id, lab_id=rec.lab_id, name=body.name, **geom)
    else:
        a = Equipment(id=body.asset_id, lab_id=rec.lab_id, name=body.name, category=body.category, kind=body.kind,
                      status="ok", **geom)
    db.add(a)
    inst["matched_asset"] = body.asset_id
    rec.result = {**rec.result}
    log(db, rec.lab_id, user.id, "workstation" if body.kind == "bench" else "machine", body.asset_id, "created",
        note=f"from reconstruction #{rec.id}")
    db.commit()
    hub.queue({"type": "refresh", "lab_id": rec.lab_id})
    await hub.flush()
    return {"ok": True, "asset_id": body.asset_id}
