from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db import ActivityLog, Equipment, Incident, Material, Quest, Role, User
from ..i18n import DEFAULT_LANG, tr
from .assets import asset

FIX_ACTIONS = ("fix", "service", "calibration")


def recommend_helpers(db: Session, equipment_id: str, exclude: str | None = None, limit: int = 3,
                      lang: str = DEFAULT_LANG) -> list[dict]:
    e = asset(db, equipment_id)
    if not e:
        return []
    text = f"{e.id} {e.name} {getattr(e, 'category', '')} {getattr(e, 'kind', '')}".lower()
    category = getattr(e, "category", None)
    similar_ids = {x.id for x in db.query(Equipment).filter_by(category=category)} if category else {e.id}
    recent = datetime.now() - timedelta(days=120)
    out = []
    for u in db.query(User).all():
        if u.id == exclude:
            continue
        score, reasons = 0.0, []
        logs = db.query(ActivityLog).filter(ActivityLog.user_id == u.id, ActivityLog.target_id == e.id).all()
        uses = sum(1 for r in logs if r.action == "use")
        fixes = sum(1 for r in logs if r.action in FIX_ACTIONS)
        solved = db.query(Incident).filter(Incident.equipment_id == e.id, Incident.resolver_id == u.id,
                                           Incident.status == "resolved").count()
        similar = db.query(Incident).filter(Incident.equipment_id.in_(similar_ids - {e.id}),
                                            Incident.resolver_id == u.id).count()
        helped = (db.query(Quest).filter(Quest.assignee_id == u.id, Quest.source == "social",
                                         Quest.status == "done").count())
        skill = [s for s in u.skills if s in text]
        recent_use = any(r.at >= recent for r in logs)
        if uses:
            score += 2 * uses
            reasons.append(tr(lang, "help.usedRecent" if recent_use else "help.used", n=uses))
        if fixes:
            score += 4 * fixes
            reasons.append(tr(lang, "help.fixed", n=fixes))
        if solved:
            score += 5 * solved
            reasons.append(tr(lang, "help.solved", n=solved))
        if similar:
            score += 3 * similar
            reasons.append(tr(lang, "help.similar", n=similar))
        if skill:
            score += 3
            reasons.append(tr(lang, "help.skill", skills=", ".join(skill)))
        if e.responsible_id == u.id:
            score += 3
            reasons.append(tr(lang, "help.responsible"))
        if helped:
            score += min(helped, 3)
            reasons.append(tr(lang, "help.helped", n=helped))
        if u.lab_id == e.lab_id:
            score += 1
            reasons.append(tr(lang, "help.nearby"))
        score += 1 if u.online else -2
        if u.role == "intern":
            score -= 3
        if score > 1:
            out.append({"user_id": u.id, "name": u.name, "role": u.role, "online": bool(u.online),
                        "score": score, "reasons": reasons})
    out.sort(key=lambda r: -r["score"])
    top = out[:limit]
    best = top[0]["score"] if top else 1
    for r in top:
        r["match"] = "high" if r["score"] >= 0.7 * best else "good"
    return top


def competence_map(db: Session, lab_id: str) -> list[dict]:
    users = db.query(User).filter_by(lab_id=lab_id).all()
    cats = {e.id: e.category for e in db.query(Equipment).filter_by(lab_id=lab_id)}
    mats = {m.id for m in db.query(Material).filter_by(lab_id=lab_id)}
    out = []
    for u in users:
        areas: dict[str, float] = defaultdict(float)
        for s in u.skills:
            areas[s] += 2
        for r in db.query(ActivityLog).filter_by(user_id=u.id).all():
            if r.target_id in cats:
                areas[cats[r.target_id].lower()] += 2 if r.action in FIX_ACTIONS else 1
            elif r.target_id in mats:
                areas["inventory"] += 0.5
        solved = db.query(Incident).filter_by(resolver_id=u.id, status="resolved").all()
        for i in solved:
            areas[(cats.get(i.equipment_id) or "general").lower()] += 3
            areas["problem solving"] += 1
        helped = db.query(Quest).filter_by(assignee_id=u.id, source="social", status="done").count()
        if helped:
            areas["mentoring"] += 2 * helped
        top = sorted(areas.items(), key=lambda kv: -kv[1])[:5]
        out.append({"user_id": u.id, "name": u.name, "role": u.role, "online": bool(u.online),
                    "areas": [{"area": a, "score": round(s, 1)} for a, s in top],
                    "go_to_for": [a for a, s in top if s >= 4][:3]})
    return out


ROLE_TIPS = ("intern", "service", "leader", "manager", "technician", "engineer")


def onboarding(db: Session, u: User, lang: str = DEFAULT_LANG) -> dict:
    mentor = db.get(User, u.mentor_id) if u.mentor_id else None
    roles = [{"id": r.id, "name": r.name, "description": r.description, "responsibilities": r.responsibilities,
              "people": [x.name for x in db.query(User).filter_by(role=r.id, lab_id=u.lab_id)]}
             for r in db.query(Role).all()]
    starter = (db.query(Quest).filter(Quest.lab_id == u.lab_id, Quest.status == "open",
                                      Quest.category.in_(["knowledge", "daily"]), Quest.priority != "high")
               .limit(3).all())
    first_uses = Counter(r.target_id for r in db.query(ActivityLog).filter_by(user_id=u.id, action="use"))
    return {
        "user_id": u.id, "done": bool(u.onboarding_done),
        "tips": [{"title": tr(lang, f"onb.{k}.t"), "body": tr(lang, f"onb.{k}.b")}
                 for k in ["1", "2", "3", "4", "5"] + ([u.role] if u.role in ROLE_TIPS else [])],
        "mentor": {"id": mentor.id, "name": mentor.name, "role": mentor.role} if mentor else None,
        "who_does_what": roles,
        "starter_quests": [{"id": q.id, "title": q.title} for q in starter],
        "instruments_used": len(first_uses),
    }
