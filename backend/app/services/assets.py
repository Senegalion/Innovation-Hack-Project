from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..db import ActivityLog, Equipment, Incident, Material, Sample, Workstation
from ..deps import name_of, ser

ASSET_LOG_TARGETS = ("machine", "workstation")


def asset(db: Session, asset_id: str | None) -> Equipment | Workstation | None:
    if not asset_id:
        return None
    return db.get(Equipment, asset_id) or db.get(Workstation, asset_id)


def asset_type(a) -> str:
    return "workstation" if isinstance(a, Workstation) else "machine"


def workstation_as_equipment(w: Workstation) -> dict:
    return {
        **ser(w), "category": "Workstation", "kind": "bench", "serial": "", "storage_class": None,
        "last_check": None, "uncertainty": "", "last_service": None, "next_service": None, "cert_expiry": None,
        "inspection_interval_days": 0, "reading": "", "manual": "", "workstation_id": None,
    }


def asset_dict(db: Session, a) -> dict:
    base = workstation_as_equipment(a) if isinstance(a, Workstation) else ser(a)
    last_use = last_log(db, a.id, ["use"])
    last_svc = last_log(db, a.id, ["service", "calibration", "fix"])
    return {
        **base,
        "asset_type": asset_type(a),
        "responsible": name_of(db, a.responsible_id),
        "last_used_by": name_of(db, last_use.user_id) if last_use else None,
        "last_used_at": last_use.at.isoformat() if last_use else None,
        "last_serviced_by": name_of(db, last_svc.user_id) if last_svc else None,
        "open_incidents": db.query(Incident).filter_by(equipment_id=a.id, status="open").count(),
    }


def lab_assets(db: Session, lab_id: str) -> list:
    return db.query(Workstation).filter_by(lab_id=lab_id).all() + db.query(Equipment).filter_by(lab_id=lab_id).all()


def log(db: Session, lab_id: str | None, user_id: str | None, target_type: str, target_id: str, action: str,
        note: str = "", amount: float = 0, data: dict | None = None, at: datetime | None = None) -> ActivityLog:
    entry = ActivityLog(lab_id=lab_id, user_id=user_id, target_type=target_type, target_id=target_id,
                        action=action, note=note, amount=amount, data=data or {})
    if at:
        entry.at = at
    db.add(entry)
    return entry


def last_log(db: Session, target_id: str, actions: list[str]) -> ActivityLog | None:
    return (db.query(ActivityLog).filter(ActivityLog.target_id == target_id, ActivityLog.action.in_(actions))
            .order_by(ActivityLog.at.desc()).first())


def logs_for(db: Session, target_id: str, limit: int = 100) -> list[dict]:
    rows = (db.query(ActivityLog).filter_by(target_id=target_id).order_by(ActivityLog.at.desc()).limit(limit).all())
    return [{"id": r.id, "kind": r.action, "action": r.action, "note": r.note, "amount": r.amount, "data": r.data,
             "at": r.at.isoformat(), "user_id": r.user_id, "user": name_of(db, r.user_id)} for r in rows]


def locate(db: Session, any_id: str) -> dict | None:
    a = asset(db, any_id)
    if a:
        return {"id": a.id, "lab_id": a.lab_id, "x": a.x, "z": a.z, "name": a.name, "asset_id": a.id}
    m = db.get(Material, any_id)
    if m:
        loc = locate(db, m.location_id)
        return {**loc, "id": m.id, "name": m.name} if loc else None
    s = db.get(Sample, any_id)
    if s:
        loc = locate(db, s.location_id)
        return {**loc, "id": s.id, "name": s.label} if loc else None
    return None


def predict_maintenance(db: Session, e: Equipment) -> dict:
    issue_times = sorted(
        [r.at for r in db.query(ActivityLog).filter(ActivityLog.target_id == e.id,
                                                    ActivityLog.action.in_(["issue"])).all()]
        + [i.at for i in db.query(Incident).filter_by(equipment_id=e.id).all()]
    )
    uniq = []
    for t in issue_times:
        if not uniq or (t - uniq[-1]).total_seconds() > 3600 * 6:
            uniq.append(t)
    gaps = [(b - a).days for a, b in zip(uniq, uniq[1:]) if (b - a).days > 0]
    mtbf = round(sum(gaps) / len(gaps), 1) if gaps else None
    predicted_issue = (uniq[-1] + timedelta(days=mtbf)).date().isoformat() if mtbf else None
    candidates = [d for d in [e.next_service, e.cert_expiry,
                              (e.last_check + timedelta(days=e.inspection_interval_days)) if e.last_check else None] if d]
    next_inspection = min(candidates) if candidates else None
    reason = None
    if next_inspection:
        reason = ("certificate" if next_inspection == e.cert_expiry else
                  "service" if next_inspection == e.next_service else "verification")
    return {
        "failures_recorded": len(uniq),
        "mtbf_days": mtbf,
        "predicted_next_issue": predicted_issue,
        "next_inspection": next_inspection.isoformat() if next_inspection else None,
        "next_inspection_reason": reason,
        "days_to_inspection": (next_inspection - date.today()).days if next_inspection else None,
    }
