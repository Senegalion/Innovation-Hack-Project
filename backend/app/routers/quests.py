from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Experiment, Incident, Lab, Message, Quest, User
from ..deps import current_user, get_db, name_of, require, ser
from ..i18n import DEFAULT_LANG, get_lang, render, tr
from ..realtime import hub, notify
from ..services.assets import asset, log
from ..services.gamification import award, quest_rule, settle_challenges
from ..services.quests import generate_quests, personalize

router = APIRouter(prefix="/api", tags=["quests"])

PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def quest_dict(db: Session, q: Quest, lang: str = DEFAULT_LANG) -> dict:
    a = asset(db, q.target_id)
    return {**ser(q), "title": render(lang, q.tpl, "t", q.title), "description": render(lang, q.tpl, "d", q.description),
            "location": a.name if a else None, "assignee": name_of(db, q.assignee_id),
            "created_by_name": name_of(db, q.created_by)}


def lab_leader(db: Session, lab_id: str, exclude: str | None = None) -> User | None:
    for access in ("leader", "admin"):
        u = db.query(User).filter(User.lab_id == lab_id, User.access == access, User.id != exclude).first()
        if u:
            return u
    lab = db.get(Lab, lab_id)
    return db.get(User, lab.manager_id) if lab else None


@router.get("/quests")
def quests(lab_id: str, user_id: str, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    generate_quests(db, lab_id)
    user = db.get(User, user_id)
    today = date.today()
    rows = db.query(Quest).filter_by(lab_id=lab_id).all()
    mine = [quest_dict(db, q, lang) for q in rows if q.assignee_id == user_id and q.status in ("accepted", "open", "snoozed")]
    pool = [quest_dict(db, q, lang) for q in rows if q.assignee_id is None and q.status == "open"
            and not (q.source == "social" and q.created_by == user_id)]
    done = [quest_dict(db, q, lang) for q in rows if q.assignee_id == user_id and q.status == "done"
            and (q.completed_at or q.created_at).date() >= today - timedelta(days=1)]
    mine.sort(key=lambda q: (PRIORITY.get(q["priority"], 9), q["due"] or "9999"))
    pool = personalize(db, user, pool, lang)
    return {
        "mine": mine, "pool": pool, "done": done,
        "projects": [{"id": x.id, "code": x.code, "title": x.title, "lead": name_of(db, x.lead_id),
                      "next_run": min((d for d in x.dates if d >= today.isoformat()), default=None),
                      "quests": [quest_dict(db, q, lang) for q in rows if q.experiment_id == x.id]}
                     for x in db.query(Experiment).filter_by(lab_id=lab_id)],
        "challenges": settle_challenges(db, lab_id),
    }


class QuestIn(BaseModel):
    lab_id: str
    title: str
    created_by: str | None = None
    description: str = ""
    category: str = "daily"
    priority: str = "medium"
    xp: int = 20
    minutes: int = 15
    target_id: str | None = None
    material_id: str | None = None
    experiment_id: str | None = None
    assignee_id: str | None = None
    due: date | None = None


@router.post("/quests")
async def create_quest(body: QuestIn, db: Session = Depends(get_db), user: User = Depends(require("leader"))):
    data = body.model_dump()
    data["created_by"] = user.id
    q = Quest(source="leader", status="accepted" if body.assignee_id else "open", **data)
    db.add(q)
    db.flush()
    if body.assignee_id:
        notify(db, [body.assignee_id], "quest_assigned", tr(DEFAULT_LANG, "n.questAssigned", who=user.name, title=q.title),
               q.description, "quest", q.id, exclude=user.id)
    log(db, q.lab_id, user.id, "quest", str(q.id), "created", note=q.title)
    db.commit()
    hub.queue({"type": "quests", "lab_id": body.lab_id})
    await hub.flush()
    return quest_dict(db, q)


class QuestAction(BaseModel):
    user_id: str | None = None
    action: str
    reason: str = ""


@router.post("/quests/{qid}/action")
async def quest_action(qid: int, body: QuestAction, db: Session = Depends(get_db),
                       header_user: User | None = Depends(current_user)):
    q = db.get(Quest, qid)
    if not q:
        raise HTTPException(404, "Quest not found")
    user = header_user or (db.get(User, body.user_id) if body.user_id else None)
    if not user:
        raise HTTPException(401, "Unknown user")
    xp = 0
    a = body.action
    if a == "accept":
        q.assignee_id, q.status = user.id, "accepted"
    elif a == "reject":
        q.status, q.reject_reason = "rejected", body.reason or "No reason given"
        if q.created_by:
            notify(db, [q.created_by], "quest_rejected", tr(DEFAULT_LANG, "n.questRejected", who=user.name, title=q.title),
                   q.reject_reason,
                   "quest", q.id, exclude=user.id)
    elif a == "snooze":
        q.status, q.due = "snoozed", (q.due or date.today()) + timedelta(days=1)
    elif a == "unassign":
        q.assignee_id, q.status = None, "open"
    elif a == "delegate":
        leader = lab_leader(db, q.lab_id, exclude=user.id)
        if not leader:
            raise HTTPException(409, "No leader available")
        q.assignee_id, q.status = leader.id, "accepted"
        notify(db, [leader.id], "quest_delegated", tr(DEFAULT_LANG, "n.questDelegated", who=user.name, title=q.title),
               body.reason, "quest", q.id)
    elif a == "problem":
        q.problem = body.reason or "Problem reported"
        notify(db, [q.created_by or (lab_leader(db, q.lab_id) or user).id], "quest_problem",
               tr(DEFAULT_LANG, "n.questProblem", title=q.title), q.problem, "quest", q.id, exclude=user.id)
    elif a == "escalate":
        q.status = "escalated"
        lab = db.get(Lab, q.lab_id)
        loc = asset(db, q.target_id)
        db.add(Incident(lab_id=q.lab_id, equipment_id=q.target_id if loc else None, reporter_id=user.id,
                        category="other", priority="medium", x=loc.x if loc else None, z=loc.z if loc else None,
                        description=tr(DEFAULT_LANG, "esc.incident", title=q.title, reason=body.reason)))
        db.add(Message(channel=f"dm:{':'.join(sorted([user.id, lab.manager_id]))}", sender_id=user.id,
                       text=tr(DEFAULT_LANG, "esc.dm", title=q.title, reason=body.reason or tr(DEFAULT_LANG, "esc.default"))))
        notify(db, [lab.manager_id], "escalation", tr(DEFAULT_LANG, "n.escalation", who=user.name, title=q.title),
               body.reason, "quest", q.id)
    elif a == "complete":
        q.assignee_id = q.assignee_id or user.id
        q.status = "done"
        q.completed_at = datetime.now()
        xp = award(db, q.assignee_id, quest_rule(q), q.lab_id, q.title, points=q.xp, ref=f"quest:{q.id}")
        if q.created_by and q.created_by != q.assignee_id:
            notify(db, [q.created_by], "quest_done", tr(DEFAULT_LANG, "n.questDone", who=name_of(db, q.assignee_id), title=q.title),
                   "", "quest", q.id)
    else:
        raise HTTPException(422, f"Unknown action {a}")
    log(db, q.lab_id, user.id, "quest", str(q.id), a, note=body.reason)
    db.commit()
    hub.queue({"type": "quests", "lab_id": q.lab_id})
    await hub.flush()
    return {"ok": True, "xp": xp, "status": q.status, "assignee_id": q.assignee_id}
