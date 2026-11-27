import math
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..db import Equipment, Experiment, Incident, Material, Message, Quest, User
from ..deps import first_name
from ..i18n import DEFAULT_LANG, render, tr
from .assets import asset, locate, predict_maintenance
from .forecast import forecast_material


def upsert(db: Session, key: str, t: str | None = None, d: str | None = None, p: dict | None = None,
           **kw) -> Quest | None:
    if db.query(Quest).filter_by(dedupe_key=key).first():
        return None
    if t:
        tpl = {"t": t, "p": p or {}}
        if d:
            tpl["d"] = d
        kw["tpl"] = tpl
        kw["title"] = render(DEFAULT_LANG, tpl, "t", kw.get("title", ""))
        kw["description"] = render(DEFAULT_LANG, tpl, "d", kw.get("description", ""))
    q = Quest(dedupe_key=key, **kw)
    db.add(q)
    return q


def location_name(db: Session, asset_id: str | None) -> str:
    a = asset(db, asset_id)
    return a.name if a else (asset_id or "")


def generate_quests(db: Session, lab_id: str):
    today = date.today()
    tag = today.isoformat()
    exps = db.query(Experiment).filter_by(lab_id=lab_id).all()
    service_user = db.query(User).filter_by(lab_id=lab_id, role="service").first()

    for m in db.query(Material).filter_by(lab_id=lab_id):
        f = forecast_material(m, exps, db)
        loc = location_name(db, m.location_id)
        if "expiring" in f["alerts"] or "expired" in f["alerts"]:
            needed = [e.code for e in exps if any(u["material_id"] == m.id for u in e.usage)
                      and any(date.fromisoformat(x) >= today for x in e.dates)]
            upsert(db, f"exp:{m.id}:{m.expires}", "q.exp.title", "q.exp.descNeeded" if needed else "q.exp.descPlan",
                   {"name": m.name, "days": f["days_to_expiry"], "lot": m.lot, "location": loc,
                    "codes": ", ".join(needed)},
                   lab_id=lab_id, source="inventory", category="esg", priority="high", xp=25, minutes=5,
                   target_id=m.location_id, material_id=m.id, due=m.expires)
        if "reorder" in f["alerts"] or "low_stock" in f["alerts"]:
            upsert(db, f"ord:{m.id}:{f['order_by'] or tag}", "q.ord.title", "q.ord.desc",
                   {"name": m.name, "date": f["order_by"] or tag, "planned": f["planned_use_30d"], "unit": m.unit,
                    "below": f["below_min_on"] or "—", "lead": m.lead_time_days, "qty": f["suggested_order_qty"]},
                   lab_id=lab_id, source="inventory", category="daily", priority="high", xp=20, minutes=10,
                   target_id=m.location_id, material_id=m.id,
                   due=date.fromisoformat(f["order_by"]) if f["order_by"] else today)
        if "missing_sds" in f["alerts"]:
            upsert(db, f"sds:{m.id}", "q.sds.title", "q.sds.desc", {"name": m.name},
                   lab_id=lab_id, source="system", category="daily", priority="medium", xp=15, minutes=5,
                   target_id=m.location_id, material_id=m.id, due=today)
        if "wrong_location" in f["alerts"]:
            upsert(db, f"loc:{m.id}:{m.location_id}", "q.loc.title", "q.loc.desc",
                   {"name": m.name, "required": f"key:storage.{m.storage_requirement}", "location": loc},
                   lab_id=lab_id, source="system", category="daily", priority="high", xp=20, minutes=5,
                   target_id=m.location_id, material_id=m.id, due=today)
        if "quantity_mismatch" in f["alerts"]:
            qi = f["quantity_issue"]
            upsert(db, f"qty:{m.id}:{qi['at'][:10]}", "q.qty.title", "q.qty.desc",
                   {"name": m.name, "observed": qi["observed"], "expected": qi["expected"], "unit": m.unit},
                   lab_id=lab_id, source="inventory", category="daily", priority="medium", xp=15, minutes=10,
                   target_id=m.location_id, material_id=m.id, due=today)

    for e in db.query(Equipment).filter_by(lab_id=lab_id):
        if e.next_service and (e.next_service - today).days <= 7:
            upsert(db, f"svc:{e.id}:{e.next_service}", "q.svc.title", "q.svc.desc",
                   {"name": e.name, "date": e.next_service.isoformat()},
                   lab_id=lab_id, source="calendar", category="weekly", priority="medium", xp=30, minutes=30,
                   target_id=e.id, due=e.next_service, assignee_id=service_user.id if service_user else None,
                   status="accepted" if service_user else "open")
        if e.cert_expiry and (e.cert_expiry - today).days <= 7:
            upsert(db, f"cert:{e.id}:{e.cert_expiry}", "q.cert.title", "q.cert.desc",
                   {"name": e.name, "date": e.cert_expiry.isoformat()},
                   lab_id=lab_id, source="calendar", category="daily", priority="high", xp=25, minutes=10,
                   target_id=e.id, due=e.cert_expiry)
        if e.last_check and (today - e.last_check).days > 60:
            upsert(db, f"chk:{e.id}:{e.last_check}", "q.chk.title", "q.chk.desc",
                   {"name": e.name, "date": e.last_check.isoformat(), "range": e.uncertainty or "key:q.chk.spec"},
                   lab_id=lab_id, source="system", category="daily", priority="medium", xp=30, minutes=15,
                   target_id=e.id, due=today)
        pm = predict_maintenance(db, e)
        if pm["predicted_next_issue"] and 0 <= (date.fromisoformat(pm["predicted_next_issue"]) - today).days <= 14:
            upsert(db, f"pred:{e.id}:{pm['predicted_next_issue']}", "q.pred.title", "q.pred.desc",
                   {"name": e.name, "mtbf": pm["mtbf_days"], "date": pm["predicted_next_issue"]},
                   lab_id=lab_id, source="system", category="weekly", priority="medium", xp=30, minutes=20,
                   target_id=e.id, due=date.fromisoformat(pm["predicted_next_issue"]))

    for i in db.query(Incident).filter_by(lab_id=lab_id, status="open"):
        upsert(db, f"inc:{i.id}", "q.inc.title", "q.inc.desc",
               {"text": i.description[:60], "category": f"key:cat.{i.category}",
                "target": location_name(db, i.equipment_id) or "—"},
               lab_id=lab_id, source="system", category="emergency" if i.priority in ("high", "critical") else "daily",
               priority=i.priority, xp=40, minutes=30, target_id=i.equipment_id, due=today)

    for msg in db.query(Message).filter_by(help_request=1):
        if not msg.channel.startswith("eq:"):
            continue
        a = asset(db, msg.channel[3:])
        if not a or a.lab_id != lab_id:
            continue
        who = db.get(User, msg.sender_id)
        upsert(db, f"help:{msg.id}", "q.help.title", None, {"who": first_name(who.name) if who else "?", "name": a.name},
               description=f"„{msg.text}”", lab_id=lab_id, source="social", category="team", priority="medium",
               xp=40, minutes=15, target_id=a.id, due=today, created_by=msg.sender_id)
    db.commit()


def anchors_for(db: Session, user: User, lang: str = DEFAULT_LANG) -> list[dict]:
    today = date.today()
    out = []
    for q in db.query(Quest).filter_by(assignee_id=user.id, status="accepted"):
        loc = locate(db, q.target_id) if q.target_id else None
        if loc:
            out.append({**loc, "why_key": "anchor.quest", "why_params": {"title": render(lang, q.tpl, "t", q.title)},
                        "quest_id": q.id})
    for e in db.query(Experiment).filter_by(lab_id=user.lab_id):
        if user.id != e.lead_id and user.id not in (e.members or []):
            continue
        if not any(today <= date.fromisoformat(d) <= today + timedelta(days=2) for d in e.dates):
            continue
        for eid in e.equipment_ids:
            loc = locate(db, eid)
            if loc:
                out.append({**loc, "why_key": "anchor.exp", "why_params": {"code": e.code, "name": loc["name"]}})
    return out


def personalize(db: Session, user: User | None, quests: list[dict], lang: str = DEFAULT_LANG) -> list[dict]:
    if not user:
        return quests
    anchors = anchors_for(db, user, lang)
    prio = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    for q in quests:
        score, reasons = prio.get(q["priority"], 1), []
        loc = locate(db, q["target_id"]) if q.get("target_id") else None
        if loc and anchors:
            near = min(anchors, key=lambda a: math.hypot(a["x"] - loc["x"], a["z"] - loc["z"]))
            why = tr(lang, near["why_key"], **near["why_params"])
            dist = math.hypot(near["x"] - loc["x"], near["z"] - loc["z"])
            if near["id"] != loc["id"] and dist <= 6:
                score += 3 - dist / 3
                reasons.append(tr(lang, "reason.near", m=f"{dist:.0f}", why=why))
            elif near["id"] == loc["id"]:
                score += 3
                reasons.append(tr(lang, "reason.same", why=why))
        text = f"{q['title']} {q.get('location') or ''} {q.get('target_id') or ''}".lower()
        skills = [s for s in user.skills if s in text]
        if skills:
            score += 2
            reasons.append(tr(lang, "reason.skills", skills=", ".join(skills)))
        if user.role == "intern" and q["category"] == "knowledge":
            score += 1
            reasons.append(tr(lang, "reason.learning"))
        if q["source"] == "social" and user.role != "intern":
            score += 1
        q["recommendation_score"] = round(score, 2)
        q["reason"] = "; ".join(reasons) or None
    quests.sort(key=lambda q: -q.get("recommendation_score", 0))
    return quests
