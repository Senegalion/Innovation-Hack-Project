from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..db import ActivityLog, Equipment, Experiment, Material
from ..i18n import DEFAULT_LANG, tr

COMPATIBLE_STORAGE = {
    "general": None,
    "flammables": {"flammables"},
    "acids": {"acids"},
    "cold": {"cold", "frozen"},
    "frozen": {"frozen"},
}


def storage_issue(db: Session, m: Material, lang: str = DEFAULT_LANG) -> str | None:
    allowed = COMPATIBLE_STORAGE.get(m.storage_requirement or "general")
    if not allowed:
        return None
    loc = db.get(Equipment, m.location_id)
    if not loc or loc.storage_class not in allowed:
        where = loc.name if loc else m.location_id
        return tr(lang, "q.loc.desc", name=m.name, required=tr(lang, f"storage.{m.storage_requirement}"),
                  location=where)
    return None


def quantity_issue(db: Session, m: Material) -> dict | None:
    check = (db.query(ActivityLog).filter_by(target_id=m.id, action="check").order_by(ActivityLog.at.desc()).first())
    if not check or "observed" not in (check.data or {}):
        return None
    expected = check.data.get("expected", m.quantity)
    observed = check.data["observed"]
    diff = observed - expected
    if abs(diff) > max(0.05 * max(expected, 1e-9), 1e-9):
        return {"expected": expected, "observed": observed, "diff": round(diff, 3), "at": check.at.isoformat()}
    return None


def forecast_material(m: Material, experiments: list[Experiment], db: Session | None = None,
                      lang: str = DEFAULT_LANG) -> dict:
    events = []
    for e in experiments:
        for u in e.usage:
            if u["material_id"] == m.id:
                events += [(date.fromisoformat(dt), u["amount"], e.code) for dt in e.dates]
    events.sort()
    today = date.today()
    qty = m.quantity
    below_min = empty = None
    planned_30d = 0.0
    runs = []
    for dt, amount, code in events:
        if dt < today:
            continue
        if dt <= today + timedelta(days=30):
            planned_30d += amount
        qty -= amount
        runs.append({"date": dt.isoformat(), "experiment": code, "amount": amount, "remaining": round(qty, 3)})
        if below_min is None and qty < m.min_stock:
            below_min = dt
        if empty is None and qty <= 0:
            empty = dt
    order_by = (below_min - timedelta(days=m.lead_time_days)) if below_min else None
    days_to_expiry = (m.expires - today).days if m.expires else None
    unused_at_expiry = None
    if m.expires:
        used_before_expiry = sum(a for dt, a, _ in events if today <= dt <= m.expires)
        unused_at_expiry = round(max(0.0, m.quantity - used_before_expiry), 3)
    alerts = []
    if days_to_expiry is not None and days_to_expiry < 0:
        alerts.append("expired")
    elif days_to_expiry is not None and days_to_expiry <= 14:
        alerts.append("expiring")
    if m.quantity < m.min_stock:
        alerts.append("low_stock")
    if order_by and (order_by - today).days <= 7:
        alerts.append("reorder")
    if not m.sds:
        alerts.append("missing_sds")
    storage = quantity = None
    if db is not None:
        storage = storage_issue(db, m, lang)
        quantity = quantity_issue(db, m)
        if storage:
            alerts.append("wrong_location")
        if quantity:
            alerts.append("quantity_mismatch")
    return {
        "planned_use_30d": round(planned_30d, 3),
        "projected_after_plan": round(qty, 3),
        "below_min_on": below_min.isoformat() if below_min else None,
        "runs_out_on": empty.isoformat() if empty else None,
        "order_by": order_by.isoformat() if order_by else None,
        "suggested_order_qty": round(max(0.0, m.min_stock * 2 - qty), 3) if below_min else 0,
        "days_to_expiry": days_to_expiry,
        "unused_at_expiry": unused_at_expiry,
        "waste_risk_eur": round((unused_at_expiry or 0) * m.unit_cost_eur, 2) if days_to_expiry is not None
        and days_to_expiry <= 30 else 0,
        "runs": runs,
        "storage_issue": storage,
        "quantity_issue": quantity,
        "alerts": alerts,
    }
