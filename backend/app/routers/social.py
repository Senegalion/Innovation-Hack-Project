import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import config
from ..db import Channel, Document, Lab, Message, Notification, Role, User
from ..deps import current_user, first_name, get_db, name_of, require, ser
from ..i18n import DEFAULT_LANG, get_lang, tr
from ..realtime import hub, notify
from ..services import inspections
from ..services.assets import asset
from ..services.gamification import award, profile
from ..services.people import competence_map, onboarding, recommend_helpers
from ..services.quests import upsert

router = APIRouter(prefix="/api", tags=["social"])


def message_dict(db: Session, m: Message) -> dict:
    atts = []
    for did in m.attachments or []:
        d = db.get(Document, did)
        if d:
            atts.append({"id": d.id, "title": d.title, "kind": d.kind, "content_type": d.content_type,
                         "url": f"/api/documents/{d.id}/download"})
    return {**ser(m), "sender": name_of(db, m.sender_id), "attachments": atts}


def channel_members(db: Session, channel: str) -> list[str]:
    if channel.startswith("dm:"):
        return channel.split(":")[1:]
    if channel.startswith("grp:"):
        c = db.get(Channel, channel)
        return c.members if c else []
    if channel.startswith("lab:"):
        return [u.id for u in db.query(User).filter_by(lab_id=channel[4:])]
    return []


@router.get("/users")
def users(db: Session = Depends(get_db)):
    return [profile(db, u) for u in db.query(User).order_by(User.xp.desc())]


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    role = db.get(Role, u.role)
    return {**profile(db, u), "role_info": ser(role) if role else None, "mentor": name_of(db, u.mentor_id)}


@router.get("/messages")
def messages(channel: str, db: Session = Depends(get_db)):
    rows = db.query(Message).filter_by(channel=channel).order_by(Message.at.asc()).limit(300).all()
    return [message_dict(db, m) for m in rows]


@router.get("/channels")
def channels(user_id: str, lab_id: str, db: Session = Depends(get_db)):
    out = []

    def last(ch):
        m = db.query(Message).filter_by(channel=ch).order_by(Message.id.desc()).first()
        return {"last_id": m.id if m else 0, "last_text": m.text if m else "", "last_at": m.at.isoformat() if m else None}

    lab = db.get(Lab, lab_id)
    if not lab:
        raise HTTPException(404, "Lab not found")
    out.append({"id": f"lab:{lab_id}", "kind": "lab", "title": lab.name, **last(f"lab:{lab_id}")})
    for c in db.query(Channel).filter_by(lab_id=lab_id):
        if user_id in c.members:
            out.append({"id": c.id, "kind": "group", "title": c.name, "members": c.members, **last(c.id)})
    for (ch,) in db.query(Message.channel).filter(Message.channel.like("eq:%")).distinct():
        a = asset(db, ch[3:])
        if a and a.lab_id == lab_id:
            out.append({"id": ch, "kind": "equipment", "title": a.name, "equipment_id": a.id, **last(ch)})
    for (ch,) in db.query(Message.channel).filter(Message.channel.like("dm:%")).distinct():
        a, b = ch.split(":")[1:]
        if user_id in (a, b):
            other = b if a == user_id else a
            out.append({"id": ch, "kind": "dm", "title": name_of(db, other), "user_id": other, **last(ch)})
    return out


class ChannelIn(BaseModel):
    lab_id: str
    name: str
    members: list[str] = []


@router.post("/channels")
async def create_channel(body: ChannelIn, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    if not user:
        raise HTTPException(401, "X-User-Id required")
    c = Channel(id=f"grp:{uuid.uuid4().hex[:8]}", lab_id=body.lab_id, name=body.name,
                members=sorted(set(body.members + [user.id])), created_by=user.id)
    db.add(c)
    notify(db, c.members, "channel_invite", tr(DEFAULT_LANG, "n.invite", who=user.name, channel=c.name), "", "channel",
           c.id, exclude=user.id)
    db.commit()
    await hub.flush()
    return ser(c)


class InviteIn(BaseModel):
    user_ids: list[str]


@router.post("/channels/{channel_id}/invite")
async def invite(channel_id: str, body: InviteIn, db: Session = Depends(get_db),
                 user: User | None = Depends(current_user)):
    c = db.get(Channel, channel_id)
    if not c:
        raise HTTPException(404, "Channel not found")
    if not user or user.id not in c.members:
        raise HTTPException(403, "Only members can invite")
    new = [u for u in body.user_ids if u not in c.members and db.get(User, u)]
    c.members = sorted(set(c.members + new))
    notify(db, new, "channel_invite", tr(DEFAULT_LANG, "n.invite", who=user.name, channel=c.name), "", "channel", c.id)
    db.add(Message(channel=c.id, sender_id=user.id,
                   text=tr(DEFAULT_LANG, "chat.invited", names=", ".join(name_of(db, u) for u in new))))
    db.commit()
    await hub.flush()
    return ser(c)


class MessageIn(BaseModel):
    channel: str
    sender_id: str
    text: str
    equipment_ref: str | None = None
    share: dict | None = None
    attachments: list[int] = []
    help_request: bool = False


ROLE_PINGS = {"@service": "service", "@manager": "manager", "@leader": "leader", "@technician": "technician",
              "@engineer": "engineer", "@intern": "intern"}


def resolve_mentions(db: Session, text: str) -> list[str]:
    low = text.lower()
    ids = [u.id for u in db.query(User) if f"@{first_name(u.name)}".lower() in low]
    for tag, role in ROLE_PINGS.items():
        if re.search(rf"{re.escape(tag)}\b", low):
            ids += [u.id for u in db.query(User).filter_by(role=role)]
    if "@here" in low or "@all" in low:
        ids += ["*"]
    return sorted(set(ids))


@router.post("/messages")
async def post_message(body: MessageIn, db: Session = Depends(get_db)):
    sender = db.get(User, body.sender_id)
    if not sender:
        raise HTTPException(404, "Sender not found")
    if body.channel.startswith("grp:"):
        c = db.get(Channel, body.channel)
        if not c or sender.id not in c.members:
            raise HTTPException(403, "Not a member of this channel")
    mentions = resolve_mentions(db, body.text)
    if "*" in mentions:
        mentions = [m for m in mentions if m != "*"] + [u for u in channel_members(db, body.channel)]
    m = Message(channel=body.channel, sender_id=sender.id, text=body.text, equipment_ref=body.equipment_ref,
                share=body.share, attachments=body.attachments, help_request=int(body.help_request),
                mentions=sorted(set(mentions)))
    db.add(m)
    db.flush()
    notify(db, m.mentions, "mention", tr(DEFAULT_LANG, "n.mention", who=sender.name), body.text[:200], "channel",
           body.channel,
           exclude=sender.id)
    if body.channel.startswith("dm:"):
        notify(db, channel_members(db, body.channel), "dm", tr(DEFAULT_LANG, "n.dm", who=sender.name), body.text[:200],
               "channel", body.channel, exclude=sender.id)
    if body.help_request and body.channel.startswith("eq:"):
        eq_id = body.channel[3:]
        helpers = recommend_helpers(db, eq_id, exclude=sender.id, limit=2)
        a = asset(db, eq_id)
        notify(db, [h["user_id"] for h in helpers], "help_request",
               tr(DEFAULT_LANG, "n.help", who=sender.name, name=a.name if a else eq_id),
               body.text[:200], "equipment", eq_id)
        if a:
            upsert(db, f"help:{m.id}", "q.help.title", None, {"who": first_name(sender.name), "name": a.name},
                   description=f"„{body.text}”", lab_id=a.lab_id, source="social", category="team",
                   priority="medium", xp=40, minutes=15, target_id=a.id, created_by=sender.id)
    if body.channel.startswith("eq:") and not body.help_request:
        asked = (db.query(Message).filter(Message.channel == body.channel, Message.help_request == 1,
                                          Message.sender_id != sender.id).count())
        if asked:
            award(db, sender.id, "knowledge_share", sender.lab_id, f"answered in {body.channel}", points=5)
    db.commit()
    payload = message_dict(db, m)
    hub.queue({"type": "message", "message": payload})
    await hub.flush()
    return payload


class HelpIn(BaseModel):
    user_id: str
    equipment_id: str
    text: str


@router.post("/help")
async def ask_help(body: HelpIn, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    if not asset(db, body.equipment_id):
        raise HTTPException(404, "Equipment not found")
    msg = await post_message(MessageIn(channel=f"eq:{body.equipment_id}", sender_id=body.user_id, text=body.text,
                                       help_request=True), db)
    return {"message": msg, "helpers": recommend_helpers(db, body.equipment_id, exclude=body.user_id, lang=lang)}


@router.get("/help/{equipment_id}")
def helpers(equipment_id: str, user_id: str | None = None, db: Session = Depends(get_db),
            lang: str = Depends(get_lang)):
    return recommend_helpers(db, equipment_id, exclude=user_id, lang=lang)


@router.get("/notifications")
def notifications(user_id: str | None = None, unread: bool = False, db: Session = Depends(get_db),
                  user: User | None = Depends(current_user)):
    uid = user_id or (user.id if user else None)
    if not uid:
        raise HTTPException(401, "user_id or X-User-Id required")
    q = db.query(Notification).filter_by(user_id=uid)
    if unread:
        q = q.filter_by(read=0)
    return [ser(n) for n in q.order_by(Notification.at.desc()).limit(100)]


@router.get("/notifications/inspections")
def inspection_list(lab_id: str | None = None, days: int | None = None, db: Session = Depends(get_db),
                    lang: str = Depends(get_lang)):
    items = inspections.due_inspections(db, lab_id, days)
    for i in items:
        i["title"] = inspections.title_for(i, lang)
    return {"enabled": True, "window_days": days if days is not None else config.INSPECTION_WINDOW_DAYS,
            "check_every_hours": config.INSPECTION_CHECK_HOURS, "items": items}


@router.post("/notifications/inspections/run")
async def inspection_run(lab_id: str | None = None, days: int | None = None, db: Session = Depends(get_db),
                         _: User = Depends(require("leader"))):
    result = inspections.send_reminders(db, lab_id, days)
    await hub.flush()
    return result


@router.post("/notifications/{nid}/read")
def read_notification(nid: int, db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if not n:
        raise HTTPException(404)
    n.read = 1
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def read_all(user_id: str, db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user_id, read=0).update({"read": 1})
    db.commit()
    return {"ok": True}


@router.get("/onboarding/{user_id}")
def get_onboarding(user_id: str, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    return onboarding(db, u, lang)


@router.post("/onboarding/{user_id}/complete")
def complete_onboarding(user_id: str, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    if not u.onboarding_done:
        u.onboarding_done = 1
        award(db, u.id, "knowledge_share", u.lab_id, "completed onboarding", points=10)
    db.commit()
    return {"ok": True}


@router.get("/competence")
def competence(lab_id: str, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    return {"note": tr(lang, "competence.note"), "people": competence_map(db, lab_id)}
