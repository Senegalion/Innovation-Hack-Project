"""AI lab assistant: Claude answers questions using the read-only lab tools.

If the Anthropic SDK or credentials are missing, or the API call fails, callers fall back to the keyword
assistant, so the app keeps working offline.
"""
import json
import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from .. import config
from ..db import Lab, User
from ..i18n import DEFAULT_LANG
from .lab_tools import TOOLS, ToolError, lab_summary, run_tool, tool_highlight

log = logging.getLogger("smartlab.ai")

MAX_TOOL_ROUNDS = 6
LANG_NAME = {"pl": "Polish", "en": "English"}

SYSTEM_PROMPT = """You are SMARTLAB, the assistant built into a laboratory's digital twin. Lab staff ask you where \
things are, how to operate or troubleshoot devices, what needs attention, and who can help.

How to work:
- Look facts up with the tools before answering. Do not invent device IDs, quantities, dates, people or \
procedures; if the tools return nothing relevant, say so and suggest who to ask (the responsible person or the \
lab manager).
- Answer in the language the user writes in. Keep it short: two to five sentences, or a short list when steps \
are needed. Plain text, no markdown headings or tables.
- Mention devices by their ID (for example HPLC-04) so the app can highlight them on the 3D map.
- When you quote a manual or SDS, name the document.
- Safety: for spills, exposure, fire or injury, tell the person to follow the lab's emergency procedure first, \
use the nearest eyewash, shower or exit, call the emergency number {emergency} for serious cases and report the \
event in the app. Never tell anyone to skip a safety step.
- Interns and newcomers should ask the responsible person before first using a device; say so when relevant."""


def _client():
    """Return an Anthropic client, or None when AI is disabled or unavailable."""
    if config.AI_ENABLED == "0":
        return None
    if config.AI_ENABLED != "1" and not (config.ANTHROPIC_API_KEY or config.ANTHROPIC_AUTH_TOKEN):
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("AI assistant enabled but the anthropic package is not installed")
        return None
    return anthropic.Anthropic(timeout=config.AI_TIMEOUT, max_retries=1)


def status() -> dict:
    return {"enabled": _client() is not None, "model": config.AI_MODEL}


def _context(db: Session, lab_id: str, user: User | None, lang: str) -> str:
    s = lab_summary(db, lab_id)
    who = f"{user.name} (role: {user.role}, user id: {user.id})" if user else "an unidentified user"
    return (f"[Context] Today is {date.today().isoformat()}. Current lab: {s['name']} ({s['code']}, {s['building']}), "
            f"manager {s['manager']}. Devices: {', '.join(s['equipment_ids'])}. Workbenches: "
            f"{', '.join(s['workbench_ids'])}. The person asking is {who}. App language: "
            f"{LANG_NAME.get(lang, 'Polish')}.")


def _history(history: list[dict] | None) -> list[dict]:
    out = []
    for h in (history or [])[-6:]:
        role, text = h.get("role"), str(h.get("content", "")).strip()
        if role in ("user", "assistant") and text:
            out.append({"role": role, "content": text[:2000]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _mentioned_asset(text: str, ids: list[str]) -> str | None:
    found = [(m.start(), i) for i in ids for m in [re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text)] if m]
    return min(found)[1] if found else None


def ask(db: Session, lab_id: str, question: str, user: User | None = None, lang: str = DEFAULT_LANG,
        history: list[dict] | None = None, client=None) -> dict | None:
    """Answer with Claude. Returns None when AI is unavailable (caller falls back to the keyword assistant)."""
    client = client or _client()
    if client is None or not db.get(Lab, lab_id):
        return None
    import anthropic

    messages = _history(history)
    messages.append({"role": "user", "content": f"{_context(db, lab_id, user, lang)}\n\n{question.strip()}"})
    system = SYSTEM_PROMPT.format(emergency=config.EMERGENCY_NUMBER)
    used, documents, highlight, material, point = [], [], None, None, None

    try:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            response = client.beta.messages.create(
                model=config.AI_MODEL,
                max_tokens=4000,
                system=system,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": config.AI_EFFORT},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason == "refusal":
                return {"enabled": True, "answer": _refusal_text(lang), "highlight": None, "documents": [],
                        "tools": used, "model": response.model}
            if response.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                used.append(block.name)
                try:
                    out = run_tool(db, lab_id, block.name, block.input if isinstance(block.input, dict) else {},
                                   user, lang)
                    highlight = tool_highlight(block.name, out) or highlight
                    if block.name == "find_in_lab":
                        material = out.get("material_id") or material
                        point = out.get("point_id") or point
                    if block.name == "get_material":
                        material = out.get("id") or material
                    if block.name == "search_documents":
                        documents += [{"document_id": d["document_id"], "title": d["title"]} for d in out["results"]]
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out, ensure_ascii=False, default=str)})
                except ToolError as e:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(e),
                                    "is_error": True})
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as e:
        log.warning("AI assistant call failed, falling back to keyword search: %s", e)
        return None

    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        text = _empty_text(lang)
    ids = lab_summary(db, lab_id)
    mentioned = _mentioned_asset(text, ids["equipment_ids"] + ids["workbench_ids"])
    seen = set()
    docs = [d for d in documents if not (d["document_id"] in seen or seen.add(d["document_id"]))]
    out = {"enabled": True, "answer": text, "highlight": mentioned or highlight, "documents": docs[:4],
           "tools": used, "model": response.model}
    if material:
        out["material"] = material
    if point:
        out["point"] = point
    return out


def _refusal_text(lang: str) -> str:
    return ("Nie mogę pomóc w tej sprawie. Zapytaj osobę odpowiedzialną albo kierownika laboratorium."
            if lang == "pl" else "I can't help with that. Please ask the responsible person or the lab manager.")


def _empty_text(lang: str) -> str:
    return ("Nie znalazłem odpowiedzi. Spróbuj zapytać inaczej albo zwróć się do kierownika laboratorium."
            if lang == "pl" else "I couldn't find an answer. Try rephrasing or ask the lab manager.")
