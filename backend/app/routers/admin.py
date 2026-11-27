from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import (ActivityLog, Challenge, Equipment, Experiment, Incident, Lab, Material, PointRule, Quest, Role,
                  Space, User, Workstation)
from ..deps import get_db, name_of, require, ser
from ..realtime import hub
from ..services.assets import asset, log
from ..services.forecast import forecast_material
from ..services.gamification import challenge_progress, profile
from ..services.people import competence_map

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/admin/stats")
def admin_stats(lab_id: str, db: Session = Depends(get_db)):
    inc = db.query(Incident).filter_by(lab_id=lab_id).all()
    hot = Counter(i.equipment_id for i in inc if i.equipment_id)
    issue_logs = Counter(r.target_id for r in db.query(ActivityLog).filter_by(lab_id=lab_id, action="issue"))
    rejected = db.query(Quest).filter_by(lab_id=lab_id, status="rejected").all()
    groups = Counter((q.title.split(" (")[0], q.reject_reason) for q in rejected)
    problems = [q for q in db.query(Quest).filter_by(lab_id=lab_id) if q.problem]
    exps = db.query(Experiment).filter_by(lab_id=lab_id).all()
    mats = db.query(Material).filter_by(lab_id=lab_id).all()
    fc = {m.id: forecast_material(m, exps, db) for m in mats}
    done = db.query(Quest).filter_by(lab_id=lab_id, status="done").all()
    lab_users = db.query(User).filter_by(lab_id=lab_id).all()
    disposals = db.query(ActivityLog).filter_by(lab_id=lab_id, target_type="material", action="dispose").all()
    saves = db.query(ActivityLog).filter_by(lab_id=lab_id, target_type="material", action="use_before_expiry").all()
    hotspots = []
    for k in set(hot) | set(issue_logs):
        a = asset(db, k)
        hotspots.append({"equipment_id": k, "name": a.name if a else k, "count": hot[k],
                         "issue_logs": issue_logs[k], "x": a.x if a else None, "z": a.z if a else None})
    hotspots.sort(key=lambda h: -(h["count"] * 2 + h["issue_logs"]))
    return {
        "hotspots": hotspots[:8],
        "incidents_open": sum(i.status == "open" for i in inc),
        "incidents_by_priority": dict(Counter(i.priority for i in inc if i.status == "open")),
        "near_misses": sum(i.category == "near_miss" for i in inc),
        "anonymous_reports": sum(i.anonymous for i in inc),
        "rejection_signals": [{"title": t, "reason": r, "count": c} for (t, r), c in groups.most_common() if c >= 2],
        "execution_problems": [{"quest_id": q.id, "title": q.title, "problem": q.problem} for q in problems],
        "esg": {
            "expiring_flagged": sum("expiring" in f["alerts"] for f in fc.values()),
            "expired": sum("expired" in f["alerts"] for f in fc.values()),
            "reorders_planned": sum(bool(f["order_by"]) for f in fc.values()),
            "waste_risk_eur": round(sum(f["waste_risk_eur"] for f in fc.values()), 2),
            "waste_disposed_eur": round(sum(d.data.get("cost_eur", 0) for d in disposals), 2),
            "saved_by_using_before_expiry_eur": round(sum(s.data.get("saved_eur", 0) for s in saves), 2),
            "esg_quests_done": sum(q.category == "esg" for q in done),
            "est_savings_eur": round(sum(s.data.get("saved_eur", 0) for s in saves)
                                     + 85 * sum(1 for q in done if (q.dedupe_key or "").startswith("exp:")), 2),
            "storage_violations": sum("wrong_location" in f["alerts"] for f in fc.values()),
        },
        "engagement": {"active_users": sum(u.online for u in lab_users), "users": len(lab_users),
                       "quests_done": len(done), "xp_total": sum(u.xp for u in lab_users)},
        "leaderboard": [{"name": u.name, "xp": u.xp, "role": u.role} for u in sorted(lab_users, key=lambda u: -u.xp)],
        "challenges": [challenge_progress(db, c) for c in db.query(Challenge).filter_by(lab_id=lab_id)],
        "competence": competence_map(db, lab_id),
    }


@router.get("/activity")
def activity(lab_id: str | None = None, target_id: str | None = None, user_id: str | None = None,
             limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(ActivityLog)
    if lab_id:
        q = q.filter_by(lab_id=lab_id)
    if target_id:
        q = q.filter_by(target_id=target_id)
    if user_id:
        q = q.filter_by(user_id=user_id)
    return [{**ser(r), "user": name_of(db, r.user_id)} for r in q.order_by(ActivityLog.at.desc()).limit(limit)]


class UserIn(BaseModel):
    id: str
    name: str
    role: str
    lab_id: str
    access: str | None = None
    skills: list[str] = []
    mentor_id: str | None = None


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    role = db.get(Role, body.role)
    if not role:
        raise HTTPException(422, "Unknown role")
    if db.get(User, body.id):
        raise HTTPException(409, "User exists")
    initials = "".join(w[0] for w in body.name.replace("Dr. ", "").split()[:2]).upper()
    u = User(id=body.id, name=body.name, initials=initials, role=role.id, access=body.access or role.access,
             skills=body.skills, lab_id=body.lab_id, mentor_id=body.mentor_id, joined=date.today(), onboarding_done=0)
    db.add(u)
    log(db, body.lab_id, admin.id, "user", u.id, "created")
    db.commit()
    return profile(db, u)


class UserPatch(BaseModel):
    role: str | None = None
    access: str | None = None
    skills: list[str] | None = None
    lab_id: str | None = None
    mentor_id: str | None = None
    online: int | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    changes = body.model_dump(exclude_none=True)
    if "role" in changes and not db.get(Role, changes["role"]):
        raise HTTPException(422, "Unknown role")
    if changes.get("access") and changes["access"] not in ("worker", "leader", "admin"):
        raise HTTPException(422, "Invalid access level")
    for k, v in changes.items():
        setattr(u, k, v)
    log(db, u.lab_id, admin.id, "user", u.id, "update", data=changes)
    db.commit()
    return profile(db, u)


@router.get("/roles")
def roles(db: Session = Depends(get_db)):
    return [{**ser(r), "people": [u.name for u in db.query(User).filter_by(role=r.id)]} for r in db.query(Role)]


class RoleIn(BaseModel):
    name: str
    access: str = "worker"
    description: str = ""
    responsibilities: list[str] = []


@router.put("/roles/{role_id}")
def upsert_role(role_id: str, body: RoleIn, db: Session = Depends(get_db), _: User = Depends(require("admin"))):
    r = db.get(Role, role_id) or Role(id=role_id)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.add(r)
    db.commit()
    return ser(r)


@router.get("/point-rules")
def point_rules(db: Session = Depends(get_db)):
    return [ser(r) for r in db.query(PointRule)]


class RuleIn(BaseModel):
    label: str | None = None
    points: int | None = None
    currency: str | None = None
    active: int | None = None


@router.put("/point-rules/{rule_id}")
def update_rule(rule_id: str, body: RuleIn, db: Session = Depends(get_db), _: User = Depends(require("admin"))):
    r = db.get(PointRule, rule_id) or PointRule(id=rule_id, label=body.label or rule_id, points=body.points or 0)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    db.add(r)
    db.commit()
    return ser(r)


@router.get("/challenges")
def challenges(lab_id: str, db: Session = Depends(get_db)):
    return [challenge_progress(db, c) for c in db.query(Challenge).filter_by(lab_id=lab_id)]


class ChallengeIn(BaseModel):
    lab_id: str
    title: str
    metric: str
    target: int
    starts: date
    ends: date
    description: str = ""
    reward_xp: int = 50


@router.post("/challenges")
def create_challenge(body: ChallengeIn, db: Session = Depends(get_db), _: User = Depends(require("leader"))):
    if body.metric not in ("expiring_reagents_flagged", "esg_quests", "near_miss_reports", "help_quests", "zero_expired"):
        raise HTTPException(422, "Unknown metric")
    c = Challenge(**body.model_dump())
    db.add(c)
    db.commit()
    return challenge_progress(db, c)


class GeometryIn(BaseModel):
    id: str
    name: str
    x: float
    z: float
    w: float
    d: float
    h: float = 0.9
    kind: str = "instrument"
    category: str = "Unassigned"
    responsible_id: str | None = None
    storage_class: str | None = None
    workstation_id: str | None = None


@router.post("/labs/{lab_id}/assets")
async def create_asset(lab_id: str, body: GeometryIn, db: Session = Depends(get_db),
                       admin: User = Depends(require("admin"))):
    if not db.get(Lab, lab_id):
        raise HTTPException(404, "Lab not found")
    if asset(db, body.id):
        raise HTTPException(409, "Asset id exists")
    geom = dict(x=body.x, z=body.z, w=body.w, d=body.d, h=body.h)
    if body.kind == "bench":
        a = Workstation(id=body.id, lab_id=lab_id, name=body.name, responsible_id=body.responsible_id, **geom)
    else:
        a = Equipment(id=body.id, lab_id=lab_id, name=body.name, kind=body.kind, category=body.category,
                      responsible_id=body.responsible_id, storage_class=body.storage_class,
                      workstation_id=body.workstation_id, status="ok", **geom)
    db.add(a)
    log(db, lab_id, admin.id, "workstation" if body.kind == "bench" else "machine", a.id, "created")
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return ser(a)


class GeometryPatch(BaseModel):
    name: str | None = None
    x: float | None = None
    z: float | None = None
    w: float | None = None
    d: float | None = None
    h: float | None = None
    category: str | None = None
    storage_class: str | None = None
    workstation_id: str | None = None
    inspection_interval_days: int | None = None
    next_service: date | None = None
    cert_expiry: date | None = None
    uncertainty: str | None = None


@router.patch("/assets/{asset_id}")
async def update_asset(asset_id: str, body: GeometryPatch, db: Session = Depends(get_db),
                       admin: User = Depends(require("admin"))):
    a = asset(db, asset_id)
    if not a:
        raise HTTPException(404)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        if hasattr(a, k):
            setattr(a, k, v)
    log(db, a.lab_id, admin.id, a.__tablename__.rstrip("s"), a.id, "update",
        data={k: (v.isoformat() if isinstance(v, date) else v) for k, v in changes.items()})
    db.commit()
    hub.queue({"type": "refresh", "lab_id": a.lab_id})
    await hub.flush()
    return ser(a)


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    a = asset(db, asset_id)
    if not a:
        raise HTTPException(404)
    if db.query(Material).filter_by(location_id=asset_id).count():
        raise HTTPException(409, "Move stored materials first")
    lab_id = a.lab_id
    db.delete(a)
    log(db, lab_id, admin.id, "asset", asset_id, "deleted")
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return {"ok": True}


class SpaceIn(BaseModel):
    id: str
    name: str
    x: float
    z: float
    w: float
    d: float
    kind: str = "zone"
    hazard: str = ""
    restricted: int = 0
    closed: int = 0
    access_roles: list[str] = []


@router.put("/labs/{lab_id}/spaces/{space_id}")
async def upsert_space(lab_id: str, space_id: str, body: SpaceIn, db: Session = Depends(get_db),
                       admin: User = Depends(require("leader"))):
    s = db.get(Space, space_id) or Space(id=space_id, lab_id=lab_id)
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(s, k, v)
    db.add(s)
    log(db, lab_id, admin.id, "space", space_id, "update", data=body.model_dump())
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return ser(s)


@router.delete("/labs/{lab_id}/spaces/{space_id}")
async def delete_space(lab_id: str, space_id: str, db: Session = Depends(get_db), _: User = Depends(require("admin"))):
    s = db.get(Space, space_id)
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return {"ok": True}


class LabPatch(BaseModel):
    name: str | None = None
    building: str | None = None
    glb_url: str | None = None
    entrance: list[float] | None = None
    width: float | None = None
    depth: float | None = None
    points: list[dict] | None = None
    manager_id: str | None = None


@router.patch("/labs/{lab_id}")
async def update_lab(lab_id: str, body: LabPatch, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise HTTPException(404)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(lab, k, v)
    log(db, lab_id, admin.id, "lab", lab_id, "update", data=changes)
    db.commit()
    hub.queue({"type": "refresh", "lab_id": lab_id})
    await hub.flush()
    return ser(lab)
