from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import segno
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Document, Equipment, Experiment, Incident, Material, Quest, Sample, User, Workstation
from ..deps import current_user, first_name, get_db, name_of, require, ser
from ..i18n import DEFAULT_LANG, get_lang, tr
from ..realtime import hub, notify
from ..services.assets import asset, asset_dict, asset_type, locate, log, logs_for, predict_maintenance
from ..services.forecast import forecast_material, storage_issue
from ..services.gamification import award
from ..services.people import recommend_helpers
from ..services.quests import upsert

router = APIRouter(prefix="/api", tags=["inventory"])

HAZARDOUS_PREFIXES = ("H22", "H30", "H31", "H33", "H34", "H35", "H36", "H37")


def get_asset(db: Session, asset_id: str):
    a = asset(db, asset_id)
    if not a:
        raise HTTPException(404, "Equipment not found")
    return a


@router.get("/equipment/{eq_id}")
def equipment_detail(eq_id: str, user_id: str | None = None, db: Session = Depends(get_db),
                     lang: str = Depends(get_lang)):
    a = get_asset(db, eq_id)
    incidents = db.query(Incident).filter_by(equipment_id=eq_id).order_by(Incident.at.desc()).all()
    on_bench = [ser(e) for e in db.query(Equipment).filter_by(workstation_id=eq_id)] if isinstance(a, Workstation) else []
    return {
        **asset_dict(db, a),
        "logs": logs_for(db, eq_id),
        "incidents": [{**ser(i), "reporter": tr(lang, "anon.name") if i.anonymous else name_of(db, i.reporter_id),
                       "resolver": name_of(db, i.resolver_id)} for i in incidents],
        "knowledge": [{"problem": i.description, "cause": i.cause, "solution": i.resolution,
                       "by": name_of(db, i.resolver_id), "date": i.at.date().isoformat()}
                      for i in incidents if i.status == "resolved" and i.resolution],
        "materials": [ser(m) for m in db.query(Material).filter_by(location_id=eq_id)],
        "samples": [ser(s) for s in db.query(Sample).filter_by(location_id=eq_id)],
        "documents": [{"id": d.id, "title": d.title, "kind": d.kind, "status": d.status}
                      for d in db.query(Document).filter_by(target_id=eq_id)],
        "on_workstation": on_bench,
        "prediction": predict_maintenance(db, a) if isinstance(a, Equipment) else None,
        "helpers": recommend_helpers(db, eq_id, exclude=user_id, lang=lang),
    }


class LogIn(BaseModel):
    user_id: str
    kind: str
    note: str = ""
    status: str | None = None
    reading: str | None = None
    within_uncertainty: bool | None = None


@router.post("/equipment/{eq_id}/logs")
async def add_equipment_log(eq_id: str, body: LogIn, db: Session = Depends(get_db)):
    a = get_asset(db, eq_id)
    user = db.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    first_use = body.kind == "use" and not any(
        entry["user_id"] == user.id and entry["kind"] == "use" for entry in logs_for(db, eq_id, 500))
    today = date.today()
    data = {}
    if isinstance(a, Equipment):
        if body.kind in ("service", "fix"):
            a.last_service = today
            a.next_service = today + timedelta(days=90)
        if body.kind in ("check", "calibration"):
            a.last_check = today
            if body.reading:
                a.reading = body.reading
            data = {"reading": body.reading, "within_uncertainty": body.within_uncertainty}
            if body.within_uncertainty is False:
                a.status = "alert"
                db.add(Incident(lab_id=a.lab_id, equipment_id=a.id, reporter_id=user.id, category="fault",
                                priority="medium", x=a.x, z=a.z,
                                description=tr(DEFAULT_LANG, "inc.outOfRange", reading=body.reading or "—")))
        if body.kind == "calibration":
            a.cert_expiry = today + timedelta(days=365)
    if body.kind == "note" and body.note:
        a.notes = body.note
    if body.kind == "issue" and isinstance(a, Equipment) and a.status == "ok":
        a.status = "maint"
    if body.status:
        a.status = body.status
    log(db, a.lab_id, user.id, asset_type(a), eq_id, body.kind, note=body.note, data=data)
    award(db, user.id, "documentation" if body.kind in ("note", "calibration", "service") else "equipment_log",
          a.lab_id, f"{body.kind} on {a.id}")
    if user.role == "intern" and body.kind == "use":
        title = tr(DEFAULT_LANG, "n.intern", who=user.name, name=a.name)
        notify(db, [a.responsible_id, user.mentor_id], "intern_activity", title,
               tr(DEFAULT_LANG, "n.internFirst") if first_use else "", "equipment", a.id, exclude=user.id)
        if first_use:
            upsert(db, f"intern:{user.id}:{a.id}", "q.intern.title", "q.intern.desc",
                   {"who": first_name(user.name), "name": a.name}, lab_id=a.lab_id, source="social",
                   category="team", priority="medium", xp=40, minutes=15, target_id=a.id, due=today,
                   created_by=user.id)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": a.lab_id})
    await hub.flush()
    return {"ok": True, "status": a.status}


class EquipmentPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    responsible_id: str | None = None
    manual: str | None = None
    reading: str | None = None


@router.patch("/equipment/{eq_id}")
async def patch_equipment(eq_id: str, body: EquipmentPatch, db: Session = Depends(get_db),
                          user: User = Depends(require("worker"))):
    a = get_asset(db, eq_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        if hasattr(a, k):
            setattr(a, k, v)
    log(db, a.lab_id, user.id, asset_type(a), eq_id, "update", data=changes)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": a.lab_id})
    await hub.flush()
    return asset_dict(db, a)


@router.get("/materials/{mat_id}")
def material_detail(mat_id: str, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    m = db.get(Material, mat_id)
    if not m:
        raise HTTPException(404, "Material not found")
    exps = db.query(Experiment).filter_by(lab_id=m.lab_id).all()
    loc = db.get(Equipment, m.location_id)
    today = date.today().isoformat()
    logs = logs_for(db, mat_id)
    last_user = next((entry for entry in logs if entry["kind"] == "take"), None)
    return {**ser(m), "forecast": forecast_material(m, exps, db, lang), "responsible": name_of(db, m.responsible_id),
            "location": loc.name if loc else m.location_id,
            "last_used_by": last_user["user"] if last_user else None,
            "used_in": [{"code": x.code, "title": x.title, "next": min((d for d in x.dates if d >= today), default=None)}
                        for x in exps if any(u["material_id"] == mat_id for u in x.usage)],
            "documents": [{"id": d.id, "title": d.title, "kind": d.kind}
                          for d in db.query(Document).filter_by(target_id=mat_id)],
            "logs": logs}


class MatLogIn(BaseModel):
    user_id: str
    kind: str
    amount: float = 0
    note: str = ""
    observed: float | None = None
    location_id: str | None = None


@router.post("/materials/{mat_id}/logs")
async def add_material_log(mat_id: str, body: MatLogIn, db: Session = Depends(get_db),
                           lang: str = Depends(get_lang)):
    m = db.get(Material, mat_id)
    user = db.get(User, body.user_id)
    if not m or not user:
        raise HTTPException(404, "Material or user not found")
    data = {}
    rule = "inventory_check"
    if body.kind == "take":
        m.quantity = max(0, round(m.quantity - body.amount, 3))
        rule = "equipment_log"
    elif body.kind == "restock":
        m.quantity = round(m.quantity + body.amount, 3)
        m.delivered = date.today()
    elif body.kind == "check":
        observed = body.observed if body.observed is not None else (body.amount or m.quantity)
        data = {"expected": m.quantity, "observed": observed}
        m.quantity = observed
    elif body.kind == "move":
        if not body.location_id or not db.get(Equipment, body.location_id):
            raise HTTPException(422, "Valid location_id required")
        data = {"from": m.location_id, "to": body.location_id}
        m.location_id = body.location_id
    elif body.kind == "dispose":
        data = {"amount": body.amount, "unit": m.unit, "cost_eur": round(body.amount * m.unit_cost_eur, 2)}
        m.quantity = max(0, round(m.quantity - body.amount, 3))
        rule = "documentation"
    elif body.kind == "use_before_expiry":
        data = {"saved_eur": round(body.amount * m.unit_cost_eur, 2)}
        m.quantity = max(0, round(m.quantity - body.amount, 3))
        rule = "waste_reduction"
    else:
        raise HTTPException(422, f"Unknown kind {body.kind}")
    log(db, m.lab_id, user.id, "material", mat_id, body.kind, note=body.note, amount=body.amount, data=data)
    award(db, user.id, rule, m.lab_id, f"{body.kind} {m.name}")
    if user.role == "intern" and body.kind == "take" and any(h.startswith(HAZARDOUS_PREFIXES) for h in m.hazards):
        notify(db, [m.responsible_id, user.mentor_id], "intern_activity",
               tr(DEFAULT_LANG, "n.internTake", who=user.name, amount=body.amount, unit=m.unit, name=m.name),
               tr(DEFAULT_LANG, "n.internHazards", list=", ".join(m.hazards)), "material", m.id, exclude=user.id)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": m.lab_id})
    await hub.flush()
    return {"ok": True, "quantity": m.quantity, "storage_issue": storage_issue(db, m, lang)}


class MaterialIn(BaseModel):
    id: str
    lab_id: str
    name: str
    location_id: str
    quantity: float
    unit: str
    min_stock: float
    cas: str = ""
    catalog_no: str = ""
    lot: str = ""
    storage_requirement: str = "general"
    lead_time_days: int = 5
    unit_cost_eur: float = 0
    expires: date | None = None
    hazards: list[str] = []
    sds: int = 0
    responsible_id: str | None = None
    notes: str = ""


@router.post("/materials")
async def create_material(body: MaterialIn, db: Session = Depends(get_db), user: User = Depends(require("worker"))):
    if db.get(Material, body.id):
        raise HTTPException(409, "Material id exists")
    m = Material(**body.model_dump(), delivered=date.today())
    db.add(m)
    log(db, m.lab_id, user.id, "material", m.id, "created", amount=m.quantity)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": m.lab_id})
    await hub.flush()
    return ser(m)


class MaterialPatch(BaseModel):
    min_stock: float | None = None
    lead_time_days: int | None = None
    expires: date | None = None
    lot: str | None = None
    sds: int | None = None
    notes: str | None = None
    responsible_id: str | None = None
    storage_requirement: str | None = None
    unit_cost_eur: float | None = None


@router.patch("/materials/{mat_id}")
async def patch_material(mat_id: str, body: MaterialPatch, db: Session = Depends(get_db),
                         user: User = Depends(require("worker"))):
    m = db.get(Material, mat_id)
    if not m:
        raise HTTPException(404)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(m, k, v)
    log(db, m.lab_id, user.id, "material", mat_id, "update",
        data={k: (v.isoformat() if isinstance(v, date) else v) for k, v in changes.items()})
    db.commit()
    hub.queue({"type": "refresh", "lab_id": m.lab_id})
    await hub.flush()
    return ser(m)


@router.get("/samples")
def samples(lab_id: str, experiment_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Sample).filter_by(lab_id=lab_id)
    if experiment_id:
        q = q.filter_by(experiment_id=experiment_id)
    return [ser(s) for s in q.all()]


@router.get("/samples/{sample_id}")
def sample_detail(sample_id: str, db: Session = Depends(get_db)):
    s = db.get(Sample, sample_id.upper())
    if not s:
        raise HTTPException(404, "Sample not found")
    return {**ser(s), "owner": name_of(db, s.owner_id), "location": locate(db, s.location_id),
            "history": logs_for(db, s.id)}


class SampleIn(BaseModel):
    lab_id: str
    label: str
    location_id: str
    owner_id: str
    experiment_id: str | None = None
    id: str | None = None
    status: str = "stored"
    notes: str = ""


@router.post("/samples")
async def create_sample(body: SampleIn, db: Session = Depends(get_db)):
    if not asset(db, body.location_id):
        raise HTTPException(422, "Unknown location")
    sid = (body.id or "").upper()
    if not sid:
        n = db.query(Sample).count() + 1
        while db.get(Sample, f"SMP-{n:04d}"):
            n += 1
        sid = f"SMP-{n:04d}"
    if db.get(Sample, sid):
        raise HTTPException(409, "Sample id exists")
    s = Sample(id=sid, collected=date.today(), **body.model_dump(exclude={"id"}))
    db.add(s)
    log(db, s.lab_id, body.owner_id, "sample", sid, "registered", note=body.label)
    db.commit()
    return {**ser(s), "qr": f"/api/qr/{sid}.svg"}


class SamplePatch(BaseModel):
    user_id: str
    location_id: str | None = None
    status: str | None = None
    notes: str | None = None


@router.patch("/samples/{sample_id}")
async def update_sample(sample_id: str, body: SamplePatch, db: Session = Depends(get_db)):
    s = db.get(Sample, sample_id.upper())
    if not s:
        raise HTTPException(404)
    data = {}
    if body.location_id and body.location_id != s.location_id:
        if not asset(db, body.location_id):
            raise HTTPException(422, "Unknown location")
        data["moved"] = [s.location_id, body.location_id]
        s.location_id = body.location_id
    if body.status and body.status != s.status:
        data["status"] = [s.status, body.status]
        s.status = body.status
    if body.notes is not None:
        s.notes = body.notes
    log(db, s.lab_id, body.user_id, "sample", s.id, "update", data=data)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": s.lab_id})
    await hub.flush()
    return ser(s)


@router.get("/scan/{code}")
def scan(code: str, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    code = code.strip().upper()
    if a := asset(db, code):
        quests = db.query(Quest).filter(Quest.target_id == a.id, Quest.status.in_(["open", "accepted"])).all()
        if user:
            log(db, a.lab_id, user.id, asset_type(a), a.id, "scan")
            db.commit()
        return {"type": "equipment", "id": a.id, "lab_id": a.lab_id, "x": a.x, "z": a.z,
                "quests": [{"id": q.id, "title": q.title, "status": q.status} for q in quests]}
    if m := db.get(Material, code):
        return {"type": "material", "id": m.id, "lab_id": m.lab_id}
    if s := db.get(Sample, code):
        return {"type": "sample", "id": s.id, "lab_id": s.lab_id, "sample": ser(s), "location": s.location_id,
                "owner": name_of(db, s.owner_id)}
    raise HTTPException(404, f"No object with ID {code}")


class NfcIn(BaseModel):
    records: list[str] = []


def nfc_candidates(tag_id: str, records: list[str]) -> list[str]:
    out = []
    for r in records:
        r = r.strip()
        if "scan=" in r:
            r = parse_qs(urlparse(r).query).get("scan", [r.split("scan=", 1)[1]])[0]
        if r and r not in out:
            out.append(r)
    if tag_id not in out:
        out.append(tag_id)
    return out


@router.post("/nfc/{tag_id}")
def nfc(tag_id: str, body: NfcIn | None = None, db: Session = Depends(get_db),
        user: User | None = Depends(current_user)):
    """Resolve an NFC tag: its NDEF records (URL with ?scan=ID or plain ID) first, then the tag ID itself."""
    for code in nfc_candidates(tag_id, body.records if body else []):
        try:
            return {"enabled": True, "via": "nfc", "tag_id": tag_id, "code": code.strip().upper(),
                    **scan(code, db, user)}
        except HTTPException:
            continue
    raise HTTPException(404, f"NFC tag {tag_id} is not linked to any station, reagent or sample")


@router.get("/qr/{code}.svg")
def qr_svg(code: str, base_url: str = "", scale: int = 6):
    payload = f"{base_url.rstrip('/')}/?scan={code}" if base_url else code
    qr = segno.make(payload, error="m")
    return Response(qr.svg_inline(scale=scale, dark="#0b0f12", light="#ffffff"), media_type="image/svg+xml")
