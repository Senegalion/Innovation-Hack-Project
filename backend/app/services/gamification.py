from collections import Counter
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from ..db import ActivityLog, Challenge, Incident, Material, Quest, User
from ..deps import ser
from .assets import log

DEFAULT_RULES = [
    ("quest_completed", "Ukończenie questa (nagroda z questa)", 20),
    ("help_colleague", "Pomoc współpracownikowi", 30),
    ("hazard_report", "Zgłoszenie zagrożenia lub near-miss", 40),
    ("documentation", "Uzupełnienie dokumentacji", 15),
    ("waste_reduction", "Ograniczenie marnotrawstwa (ESG)", 35),
    ("knowledge_share", "Podzielenie się wiedzą", 25),
    ("equipment_log", "Zapis użycia / kontroli urządzenia", 5),
    ("inventory_check", "Weryfikacja magazynu", 10),
    ("incident_resolved", "Rozwiązanie zgłoszenia", 30),
]

BADGES = [
    ("Safety Guardian", "shield", "Reported safety issues", {"hazard_report"}),
    ("Eco Hero", "leaf", "Completed ESG actions", {"waste_reduction"}),
    ("Team Player", "users", "Helped colleagues", {"help_colleague"}),
    ("Knowledge Master", "book", "Shared knowledge", {"knowledge_share", "documentation"}),
    ("Inventory Master", "package", "Kept inventory in shape", {"inventory_check"}),
]

CATEGORY_RULE = {"esg": "waste_reduction", "knowledge": "knowledge_share", "team": "help_colleague"}
SOURCE_RULE = {"inventory": "inventory_check", "social": "help_colleague"}


def rule_points(db: Session, key: str) -> int:
    from ..db import PointRule

    r = db.get(PointRule, key)
    return r.points if r and r.active else 0


def award(db: Session, user_id: str | None, rule: str, lab_id: str | None = None, note: str = "",
          points: int | None = None, ref: str | None = None) -> int:
    u = db.get(User, user_id) if user_id else None
    if not u:
        return 0
    pts = rule_points(db, rule) if points is None else points
    if pts <= 0:
        return 0
    u.xp += pts
    log(db, lab_id or u.lab_id, u.id, "user", u.id, "points", note=note or rule, amount=pts,
        data={"rule": rule, "ref": ref})
    return pts


def quest_rule(q: Quest) -> str:
    return CATEGORY_RULE.get(q.category) or SOURCE_RULE.get(q.source) or "quest_completed"


def rule_counts(db: Session, user_id: str) -> Counter:
    rows = db.query(ActivityLog).filter_by(target_type="user", target_id=user_id, action="points").all()
    return Counter(r.data.get("rule") for r in rows)


def profile(db: Session, u: User) -> dict:
    counts = rule_counts(db, u.id)
    badges = []
    for name, icon, desc, rules in BADGES:
        n = sum(counts[r] for r in rules)
        if n:
            badges.append({"name": name, "icon": icon, "desc": desc, "count": n})
    done = db.query(Quest).filter_by(assignee_id=u.id, status="done").count()
    return {**ser(u), "level": u.xp // 200 + 1, "level_progress": (u.xp % 200) / 200, "quests_done": done,
            "badges": badges}


def challenge_progress(db: Session, c: Challenge) -> dict:
    start = datetime.combine(c.starts, time.min)
    end = datetime.combine(c.ends, time.max)
    if c.metric == "expiring_reagents_flagged":
        value = (db.query(Quest).filter(Quest.lab_id == c.lab_id, Quest.status == "done",
                                        Quest.dedupe_key.like("exp:%"), Quest.completed_at >= start,
                                        Quest.completed_at <= end).count())
    elif c.metric == "esg_quests":
        value = (db.query(Quest).filter(Quest.lab_id == c.lab_id, Quest.status == "done", Quest.category == "esg",
                                        Quest.completed_at >= start, Quest.completed_at <= end).count())
    elif c.metric == "near_miss_reports":
        value = (db.query(Incident).filter(Incident.lab_id == c.lab_id, Incident.category == "near_miss",
                                           Incident.at >= start, Incident.at <= end).count())
    elif c.metric == "help_quests":
        value = (db.query(Quest).filter(Quest.lab_id == c.lab_id, Quest.status == "done", Quest.source == "social",
                                        Quest.completed_at >= start, Quest.completed_at <= end).count())
    elif c.metric == "zero_expired":
        expired = sum(1 for m in db.query(Material).filter_by(lab_id=c.lab_id) if m.expires and m.expires < date.today())
        value = c.target if expired == 0 else 0
    else:
        value = 0
    return {**ser(c), "value": value, "progress": min(1.0, value / c.target) if c.target else 0,
            "completed": value >= c.target, "active": c.starts <= date.today() <= c.ends}


def settle_challenges(db: Session, lab_id: str) -> list[dict]:
    out = []
    for c in db.query(Challenge).filter_by(lab_id=lab_id):
        p = challenge_progress(db, c)
        if p["completed"] and not c.rewarded:
            c.rewarded = 1
            for u in db.query(User).filter_by(lab_id=lab_id):
                award(db, u.id, "team_challenge", lab_id, f"Team challenge: {c.title}", points=c.reward_xp)
            p["rewarded"] = 1
        out.append(p)
    return out
