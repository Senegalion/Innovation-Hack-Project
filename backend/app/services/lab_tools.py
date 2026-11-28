"""Read-only lab tools shared by the AI assistant (Claude tool use) and the MCP server.

Every tool takes the lab it works on from the caller (the assistant knows the current lab, MCP clients pass
``lab_id``), never changes data, and returns plain JSON-serialisable dicts.
"""
from datetime import date

from sqlalchemy.orm import Session

from ..db import Equipment, Experiment, Incident, Lab, Material, Quest, User, Workstation
from ..deps import name_of, ser
from ..i18n import DEFAULT_LANG
from .assets import asset, asset_dict, lab_assets, logs_for, predict_maintenance
from .assistant import ask_assistant
from .documents import search
from .forecast import forecast_material
from .people import recommend_helpers


class ToolError(Exception):
    """Raised for bad tool input; reported back to the model or MCP client as an error result."""


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


TOOLS: list[dict] = [
    {
        "name": "find_in_lab",
        "description": "Find where something is in the current lab: a device, workbench, reagent, sample, safety "
                       "point (eyewash, shower, exit, first aid, extinguisher) or zone. Accepts Polish or English "
                       "names, IDs, CAS or catalog numbers. Returns the best match with its location.",
        "input_schema": _obj({"query": {"type": "string", "description": "What to look for, e.g. 'acetonitryl' or 'eyewash'"}},
                             ["query"]),
    },
    {
        "name": "search_documents",
        "description": "Full-text search over the lab's uploaded documentation: device manuals, SOPs and safety data "
                       "sheets (SDS). Use it for how-to, troubleshooting and safety questions. Returns text excerpts "
                       "with the document title.",
        "input_schema": _obj({
            "query": {"type": "string", "description": "Search terms, e.g. 'HPLC pressure fluctuation purge'"},
            "target_id": {"type": "string", "description": "Optional device or material ID to limit the search to its documents"},
        }, ["query"]),
    },
    {
        "name": "list_equipment",
        "description": "List devices and workbenches in the lab with their status (ok, maint, alert, off). "
                       "Optionally filter by status.",
        "input_schema": _obj({"status": {"type": "string", "enum": ["ok", "maint", "alert", "off"]}}),
    },
    {
        "name": "get_equipment",
        "description": "Full card of one device or workbench: status, responsible person, last check and its "
                       "uncertainty, service and certificate dates, who used and serviced it last, recent log "
                       "entries, open incidents and a predicted next failure / inspection.",
        "input_schema": _obj({"equipment_id": {"type": "string", "description": "Device ID, e.g. HPLC-04"}},
                             ["equipment_id"]),
    },
    {
        "name": "list_material_alerts",
        "description": "Reagents and consumables that need attention: expiring or expired, low stock, reorder date "
                       "close, missing SDS, wrong storage location or a count mismatch.",
        "input_schema": _obj({}),
    },
    {
        "name": "get_material",
        "description": "Card of one reagent: quantity, location, lot, expiry, hazards, responsible person and a "
                       "consumption forecast from planned experiments (order-by date, when it runs out).",
        "input_schema": _obj({"material_id": {"type": "string", "description": "Material ID, e.g. MAT-ACN"}},
                             ["material_id"]),
    },
    {
        "name": "find_helpers",
        "description": "Who can help with a device: colleagues ranked by past use, fixes, solved incidents, skills "
                       "and availability, with the reasons.",
        "input_schema": _obj({"equipment_id": {"type": "string"}}, ["equipment_id"]),
    },
    {
        "name": "search_knowledge_base",
        "description": "Search solved problems (problem, cause, solution, who helped) recorded when incidents were "
                       "resolved. Optionally limit to one device.",
        "input_schema": _obj({"query": {"type": "string"}, "equipment_id": {"type": "string"}}, ["query"]),
    },
    {
        "name": "list_open_incidents",
        "description": "Open safety reports and device faults in the lab, newest first, with priority and place.",
        "input_schema": _obj({}),
    },
    {
        "name": "list_quests",
        "description": "Quests (tasks) of the person asking: assigned to them, plus open quests they could pick up.",
        "input_schema": _obj({}),
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}


def _equipment(db: Session, lab_id: str, equipment_id: str):
    a = asset(db, equipment_id)
    if not a or a.lab_id != lab_id:
        raise ToolError(f"No device or workbench '{equipment_id}' in lab {lab_id}. Use list_equipment or find_in_lab.")
    return a


def _material(db: Session, lab_id: str, material_id: str) -> Material:
    m = db.get(Material, material_id)
    if not m or m.lab_id != lab_id:
        raise ToolError(f"No material '{material_id}' in lab {lab_id}. Use find_in_lab or list_material_alerts.")
    return m


def _material_card(db: Session, m: Material, lang: str) -> dict:
    exps = db.query(Experiment).filter_by(lab_id=m.lab_id).all()
    f = forecast_material(m, exps, db, lang)
    loc = asset(db, m.location_id)
    return {"id": m.id, "name": m.name, "cas": m.cas, "lot": m.lot, "quantity": m.quantity, "unit": m.unit,
            "min_stock": m.min_stock, "location_id": m.location_id, "location": loc.name if loc else None,
            "expires": m.expires.isoformat() if m.expires else None, "hazards": m.hazards, "sds": bool(m.sds),
            "responsible": name_of(db, m.responsible_id), "notes": m.notes,
            "forecast": {k: f[k] for k in ("alerts", "days_to_expiry", "planned_use_30d", "below_min_on", "runs_out_on",
                                           "order_by", "suggested_order_qty", "waste_risk_eur", "storage_issue")}}


def run_tool(db: Session, lab_id: str, name: str, args: dict, user: User | None = None,
             lang: str = DEFAULT_LANG) -> dict:
    """Execute one tool. Raises ToolError for bad input."""
    if not db.get(Lab, lab_id):
        raise ToolError(f"Unknown lab '{lab_id}'")
    args = args or {}

    if name == "find_in_lab":
        r = ask_assistant(db, lab_id, str(args.get("query", "")), lang)
        return {"answer": r["answer"], "highlight": r.get("highlight"), "material_id": r.get("material"),
                "point_id": r.get("point"), "matches": r.get("matches", [])}

    if name == "search_documents":
        r = search(db, str(args.get("query", "")), lab_id=lab_id, target_id=args.get("target_id") or None, limit=4)
        return {"results": [{"document_id": d["document_id"], "title": d["title"], "kind": d["kind"],
                             "target_id": d["target_id"], "excerpt": d["text"][:900]} for d in r["results"]]}

    if name == "list_equipment":
        status = args.get("status")
        return {"equipment": [{"id": a.id, "name": a.name, "status": a.status,
                               "category": getattr(a, "category", "Workbench"), "kind": getattr(a, "kind", "bench")}
                              for a in lab_assets(db, lab_id) if not status or a.status == status]}

    if name == "get_equipment":
        a = _equipment(db, lab_id, str(args.get("equipment_id", "")))
        card = asset_dict(db, a)
        keep = ("id", "name", "category", "kind", "status", "serial", "responsible", "last_check", "uncertainty",
                "last_service", "next_service", "cert_expiry", "reading", "notes", "last_used_by", "last_used_at",
                "last_serviced_by", "open_incidents", "workstation_id")
        out = {k: card.get(k) for k in keep if k in card}
        if isinstance(a, Equipment):
            out["prediction"] = predict_maintenance(db, a)
        out["recent_logs"] = [{"action": r["action"], "note": r["note"], "user": r["user"], "at": r["at"][:16]}
                              for r in logs_for(db, a.id, limit=8)]
        return out

    if name == "list_material_alerts":
        cards = [_material_card(db, m, lang) for m in db.query(Material).filter_by(lab_id=lab_id)]
        return {"materials": [c for c in cards if c["forecast"]["alerts"]]}

    if name == "get_material":
        return _material_card(db, _material(db, lab_id, str(args.get("material_id", ""))), lang)

    if name == "find_helpers":
        a = _equipment(db, lab_id, str(args.get("equipment_id", "")))
        return {"equipment_id": a.id, "helpers": recommend_helpers(db, a.id, exclude=user.id if user else None,
                                                                   lang=lang)}

    if name == "search_knowledge_base":
        from ..routers.incidents import knowledge

        eq = args.get("equipment_id") or None
        rows = knowledge(lab_id=lab_id, q=str(args.get("query", "")), equipment_id=eq, db=db)
        return {"entries": rows[:5]}

    if name == "list_open_incidents":
        rows = (db.query(Incident).filter_by(lab_id=lab_id, status="open").order_by(Incident.at.desc()).limit(10).all())
        return {"incidents": [{"id": i.id, "priority": i.priority, "category": i.category,
                               "description": i.description, "equipment_id": i.equipment_id,
                               "reported_at": i.at.isoformat()[:16]} for i in rows]}

    if name == "list_quests":
        if not user:
            raise ToolError("list_quests needs to know who is asking (send the X-User-Id header)")
        from ..routers.quests import quest_dict
        from .quests import generate_quests

        generate_quests(db, lab_id)
        rows = db.query(Quest).filter_by(lab_id=lab_id).all()
        fields = ("id", "title", "description", "priority", "category", "status", "due", "location", "xp")

        def slim(q: Quest) -> dict:
            d = quest_dict(db, q, lang)
            return {k: d[k] for k in fields}

        return {"today": date.today().isoformat(),
                "mine": [slim(q) for q in rows if q.assignee_id == user.id and q.status in ("accepted", "open", "snoozed")],
                "open_pool": [slim(q) for q in rows if q.assignee_id is None and q.status == "open"][:8]}

    raise ToolError(f"Unknown tool '{name}'")


def tool_highlight(name: str, result: dict) -> str | None:
    """Asset ID the 3D twin should focus after this tool ran, if any."""
    if name == "find_in_lab":
        return result.get("highlight")
    if name in ("get_equipment",):
        return result.get("id")
    if name == "find_helpers":
        return result.get("equipment_id")
    if name == "get_material":
        return result.get("location_id")
    return None


def lab_summary(db: Session, lab_id: str) -> dict:
    lab = db.get(Lab, lab_id)
    assets = lab_assets(db, lab_id)
    return {"id": lab.id, "code": lab.code, "name": lab.name, "building": lab.building,
            "manager": name_of(db, lab.manager_id),
            "equipment_ids": [a.id for a in assets if not isinstance(a, Workstation)],
            "workbench_ids": [a.id for a in assets if isinstance(a, Workstation)]}


def labs_list(db: Session) -> list[dict]:
    return [{**{k: v for k, v in ser(lab).items() if k in ("id", "code", "name", "building")},
             "manager": name_of(db, lab.manager_id)} for lab in db.query(Lab)]
