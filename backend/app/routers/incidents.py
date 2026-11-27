import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import EMERGENCY_NUMBER
from ..db import Equipment, Incident, Lab, Message, Quest, User
from ..deps import get_db, name_of, ser
from ..i18n import DEFAULT_LANG, get_lang, tr
from ..realtime import hub, notify
from ..services.assets import asset, asset_type, log
from ..services.documents import tokens
from ..services.gamification import award

router = APIRouter(prefix="/api", tags=["incidents"])

PRIORITIES = ("low", "medium", "high", "critical")
CATEGORY_AID = {"exposure": ("eyewash", "shower"), "spill": ("eyewash", "shower", "exit"),
                "fire": ("extinguisher", "exit"), "fault": ("exit",), "near_miss": ("firstaid",),
                "other": ("firstaid", "exit")}
def incident_dict(db: Session, i: Incident, lang: str = DEFAULT_LANG) -> dict:
    a = asset(db, i.equipment_id)
    return {**ser(i), "reporter": tr(lang, "anon.name") if i.anonymous else name_of(db, i.reporter_id),
            "resolver": name_of(db, i.resolver_id), "equipment": a.name if a else None}


def nearest_points(lab: Lab, x: float | None, z: float | None, kinds: tuple) -> list[dict]:
    pts = [p for p in lab.points if p["kind"] in kinds]
    if x is None or z is None:
        return [{**p, "distance_m": None} for p in pts]
    pts.sort(key=lambda p: math.hypot(p["x"] - x, p["z"] - z))
    return [{**p, "distance_m": round(math.hypot(p["x"] - x, p["z"] - z), 1)} for p in pts]


class IncidentIn(BaseModel):
    lab_id: str
    reporter_id: str
    category: str
    priority: str
    description: str = ""
    equipment_id: str | None = None
    anonymous: bool = False
    x: float | None = None
    z: float | None = None


@router.post("/incidents")
async def report_incident(body: IncidentIn, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    if body.priority not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    lab = db.get(Lab, body.lab_id)
    reporter = db.get(User, body.reporter_id)
    if not lab or not reporter:
        raise HTTPException(404, "Lab or reporter not found")
    a = asset(db, body.equipment_id)
    x, z = (a.x, a.z) if a else (body.x, body.z)
    i = Incident(lab_id=body.lab_id, equipment_id=body.equipment_id, reporter_id=body.reporter_id,
                 category=body.category, priority=body.priority, description=body.description,
                 anonymous=int(body.anonymous), x=x, z=z)
    db.add(i)
    db.flush()
    if isinstance(a, Equipment):
        if body.priority in ("high", "critical"):
            a.status = "alert"
        elif body.category == "fault" and a.status == "ok":
            a.status = "maint"
    if a:
        log(db, a.lab_id, None if body.anonymous else reporter.id, asset_type(a), a.id, "issue",
            note=f"[{body.priority}] {body.description}", data={"incident": i.id})
    award(db, reporter.id, "hazard_report", body.lab_id, f"reported {body.category}", ref=f"incident:{i.id}")
    lab_users = [u.id for u in db.query(User).filter_by(lab_id=body.lab_id)]
    targets = [u.id for u in db.query(User).filter(User.role.in_(["service", "manager"]))]
    targets += [lab.manager_id, a.responsible_id if a else None]
    if body.priority in ("high", "critical"):
        targets += [u.id for u in db.query(User).filter_by(lab_id=body.lab_id, access="leader")]
    if body.priority == "critical":
        targets += lab_users
    where = a.name if a else lab.name
    L = DEFAULT_LANG
    who = tr(L, "anon.name") if body.anonymous else reporter.name
    prio, cat = tr(L, f"pri.{body.priority}"), tr(L, f"cat.{body.category}")
    i.notified = notify(db, targets, "incident", tr(L, "inc.notifyTitle", priority=prio, category=cat, where=where),
                        f"{who}: {body.description}", "incident", i.id,
                        exclude=None if body.priority == "critical" else reporter.id)
    db.add(Message(channel=f"lab:{body.lab_id}", sender_id="system" if body.anonymous else reporter.id,
                   text=tr(L, "inc.chat", priority=prio, category=cat, where=where, text=body.description,
                           anon=tr(L, "inc.anon") if body.anonymous else ""),
                   equipment_ref=a.id if a else None, mentions=sorted({t for t in targets if t})))
    db.commit()
    hub.queue({"type": "incident", "lab_id": body.lab_id, "priority": body.priority, "category": body.category,
               "who": None if body.anonymous else reporter.name, "where": where,
               "text": f"{who}: {cat} — {where}"})
    hub.queue({"type": "refresh", "lab_id": body.lab_id})
    await hub.flush()
    out = {**incident_dict(db, i, lang), "xp": 40}
    if body.priority in ("high", "critical"):
        out["procedure"] = {
            "emergency_number": EMERGENCY_NUMBER,
            "steps": tr(lang, f"proc.{body.category if body.category in CATEGORY_AID else 'other'}",
                        phone=EMERGENCY_NUMBER),
            "nearest": nearest_points(lab, x, z, CATEGORY_AID.get(body.category, ("exit",)))[:3],
            "disclaimer": tr(lang, "proc.disclaimer"),
        }
    return out


@router.get("/incidents")
def incidents(lab_id: str, status: str | None = None, db: Session = Depends(get_db),
              lang: str = Depends(get_lang)):
    q = db.query(Incident).filter_by(lab_id=lab_id)
    if status:
        q = q.filter_by(status=status)
    return [incident_dict(db, i, lang) for i in q.order_by(Incident.at.desc()).all()]


class ResolveIn(BaseModel):
    user_id: str
    resolution: str
    cause: str = ""


@router.post("/incidents/{iid}/resolve")
async def resolve_incident(iid: int, body: ResolveIn, db: Session = Depends(get_db)):
    i = db.get(Incident, iid)
    user = db.get(User, body.user_id)
    if not i or not user:
        raise HTTPException(404)
    if user.access == "worker" and user.role not in ("service", "engineer"):
        raise HTTPException(403, "Only service, engineers, leaders or managers can resolve incidents")
    i.status, i.resolution, i.cause, i.resolver_id, i.resolved_at = (
        "resolved", body.resolution, body.cause, user.id, datetime.now())
    a = asset(db, i.equipment_id)
    if a:
        still_open = db.query(Incident).filter(Incident.equipment_id == a.id, Incident.status == "open",
                                               Incident.id != i.id).count()
        if not still_open and a.status in ("alert", "maint"):
            a.status = "ok"
        log(db, a.lab_id, user.id, asset_type(a), a.id, "fix", note=body.resolution, data={"incident": i.id})
    for q in db.query(Quest).filter_by(dedupe_key=f"inc:{iid}"):
        q.status, q.assignee_id, q.completed_at = "done", q.assignee_id or user.id, datetime.now()
    award(db, user.id, "incident_resolved", i.lab_id, f"resolved incident {i.id}")
    award(db, user.id, "knowledge_share", i.lab_id, "knowledge base entry")
    if not i.anonymous:
        notify(db, [i.reporter_id], "incident_resolved", tr(DEFAULT_LANG, "inc.resolvedTitle", name=user.name),
               body.resolution,
               "incident", i.id, exclude=user.id)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": i.lab_id})
    await hub.flush()
    return {"ok": True}


@router.get("/knowledge")
def knowledge(lab_id: str, q: str = "", equipment_id: str | None = None, db: Session = Depends(get_db)):
    rows = db.query(Incident).filter(Incident.lab_id == lab_id, Incident.status == "resolved",
                                     Incident.resolution != "")
    if equipment_id:
        rows = rows.filter_by(equipment_id=equipment_id)
    qt = set(tokens(q)) if q else set()
    out = []
    for i in rows.all():
        a = asset(db, i.equipment_id)
        text = f"{i.description} {i.cause} {i.resolution} {a.name if a else ''}"
        score = len(qt & set(tokens(text))) if qt else 1
        if score:
            out.append({"id": i.id, "problem": i.description, "cause": i.cause, "solution": i.resolution,
                        "equipment_id": i.equipment_id, "equipment": a.name if a else None,
                        "helped_by": name_of(db, i.resolver_id), "date": i.at.date().isoformat(), "score": score})
    out.sort(key=lambda r: -r["score"])
    return out
