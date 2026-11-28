"""Automatic inspection reminders: certificates, services and verification checks that are due or overdue.

`due_inspections` lists them; `send_reminders` notifies the responsible person, the service technicians and the
lab manager once per item and day. `reminder_loop` runs it in the background (INSPECTION_CHECK_HOURS).
"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from .. import config
from ..db import Equipment, Lab, Notification, SessionLocal, User
from ..deps import name_of
from ..i18n import DEFAULT_LANG, tr
from ..realtime import hub, notify

log = logging.getLogger("smartlab.inspections")

KINDS = ("certificate", "service", "verification")


def due_inspections(db: Session, lab_id: str | None = None, days: int | None = None) -> list[dict]:
    days = config.INSPECTION_WINDOW_DAYS if days is None else days
    today = date.today()
    q = db.query(Equipment)
    if lab_id:
        q = q.filter_by(lab_id=lab_id)
    items = []
    for e in q.all():
        if e.status == "off":
            continue
        dates = {
            "certificate": e.cert_expiry,
            "service": e.next_service,
            "verification": e.last_check + timedelta(days=e.inspection_interval_days) if e.last_check else None,
        }
        for kind, due in dates.items():
            if not due:
                continue
            left = (due - today).days
            if left > days:
                continue
            items.append({
                "equipment_id": e.id, "name": e.name, "lab_id": e.lab_id, "kind": kind, "due": due.isoformat(),
                "days_left": left, "overdue": left < 0, "status": e.status,
                "responsible_id": e.responsible_id, "responsible": name_of(db, e.responsible_id),
                "uncertainty": e.uncertainty if kind == "verification" else None,
            })
    items.sort(key=lambda i: (i["days_left"], i["equipment_id"], i["kind"]))
    return items


def _recipients(db: Session, item: dict) -> list[str]:
    lab = db.get(Lab, item["lab_id"])
    ids = [item["responsible_id"], lab.manager_id if lab else None]
    ids += [u.id for u in db.query(User).filter_by(role="service")]
    return [i for i in dict.fromkeys(ids) if i]


def title_for(item: dict, lang: str = DEFAULT_LANG) -> str:
    what = tr(lang, f"insp.kind.{item['kind']}")
    if item["overdue"]:
        return tr(lang, "insp.overdue", what=what, name=item["name"], n=-item["days_left"])
    if item["days_left"] == 0:
        return tr(lang, "insp.today", what=what, name=item["name"])
    return tr(lang, "insp.soon", what=what, name=item["name"], n=item["days_left"], date=item["due"])


def send_reminders(db: Session, lab_id: str | None = None, days: int | None = None) -> dict:
    """Notify about due inspections. Each item notifies each person at most once per day."""
    start = datetime.combine(date.today(), time.min)
    sent, skipped = [], 0
    for item in due_inspections(db, lab_id, days):
        title = title_for(item)
        targets = []
        for uid in _recipients(db, item):
            exists = db.query(Notification).filter(
                Notification.user_id == uid, Notification.kind == "inspection", Notification.ref_id == item["equipment_id"],
                Notification.title == title, Notification.at >= start).first()
            if exists:
                skipped += 1
            else:
                targets.append(uid)
        if not targets:
            continue
        body = tr(DEFAULT_LANG, "insp.body", due=item["due"], who=item["responsible"] or "—")
        if item["uncertainty"]:
            body += " " + tr(DEFAULT_LANG, "insp.range", range=item["uncertainty"])
        notify(db, targets, "inspection", title, body, "equipment", item["equipment_id"])
        sent.append({**item, "notified": targets, "title": title})
    db.commit()
    return {"sent": sent, "notifications": sum(len(s["notified"]) for s in sent), "skipped": skipped}


async def run_once() -> dict:
    with SessionLocal() as db:
        result = send_reminders(db)
    await hub.flush()
    if result["notifications"]:
        log.info("Inspection reminders: %s notifications for %s items", result["notifications"], len(result["sent"]))
    return result


async def reminder_loop():
    hours = config.INSPECTION_CHECK_HOURS
    if hours <= 0:
        return
    await asyncio.sleep(5)  # let startup and seeding finish
    while True:
        try:
            await run_once()
        except Exception:
            log.exception("Inspection reminder run failed")
        await asyncio.sleep(hours * 3600)
