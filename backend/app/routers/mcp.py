"""MCP server (Model Context Protocol, Streamable HTTP transport, stateless JSON responses).

Exposes the same read-only lab tools the in-app AI assistant uses, so external AI clients (Claude Desktop,
Claude Code, any MCP client) can ask SMARTLAB about equipment, reagents, documents, incidents and quests.

Connect e.g. with:  claude mcp add --transport http smartlab http://localhost:8000/mcp
"""
import copy
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from .. import config
from ..db import Lab, User
from ..deps import get_db
from ..i18n import get_lang
from ..services.lab_tools import TOOLS, ToolError, labs_list, run_tool

router = APIRouter(tags=["mcp"])

SUPPORTED_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
SERVER_INFO = {"name": "smartlab", "title": "SMARTLAB Digital Twin", "version": "0.3.0"}
INSTRUCTIONS = ("SMARTLAB laboratory digital twin. Call list_labs first to get lab IDs, then pass lab_id to the "
                "other tools (it defaults to the first lab). All tools are read-only.")

LAB_ID = {"type": "string", "description": "Lab ID from list_labs, e.g. lab-204. Defaults to the first lab."}


def mcp_tools() -> list[dict]:
    out = [{"name": "list_labs", "title": "List labs",
            "description": "List the laboratories in SMARTLAB with their IDs, names, buildings and managers.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "openWorldHint": False}}]
    for t in TOOLS:
        schema = copy.deepcopy(t["input_schema"])
        schema["properties"] = {"lab_id": LAB_ID, **schema["properties"]}
        if t["name"] == "list_quests":
            schema["properties"]["user_id"] = {"type": "string", "description": "Whose quests, e.g. u-tomek"}
        out.append({"name": t["name"], "title": t["name"].replace("_", " ").capitalize(),
                    "description": t["description"], "inputSchema": schema,
                    "annotations": {"readOnlyHint": True, "openWorldHint": False}})
    return out


def rpc_result(id_, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def rpc_error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = urlparse(origin).hostname or ""
    own = (request.headers.get("host") or "").split(":")[0]
    return host == own or host in config.MCP_ALLOWED_ORIGINS


def call_tool(db: Session, request: Request, params: dict, lang: str) -> dict:
    name = params.get("name")
    args = dict(params.get("arguments") or {})
    if name == "list_labs":
        payload = {"labs": labs_list(db)}
    else:
        lab_id = args.pop("lab_id", None)
        if not lab_id:
            first = db.query(Lab).first()
            lab_id = first.id if first else ""
        uid = args.pop("user_id", None) or request.headers.get("x-user-id")
        user = db.get(User, uid) if uid else None
        try:
            payload = run_tool(db, lab_id, name, args, user, lang)
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}],
            "isError": False}


def handle(db: Session, request: Request, msg: dict, lang: str) -> dict | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return rpc_error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    method, id_, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:  # notification (e.g. notifications/initialized): no response
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return rpc_result(id_, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS})
    if method == "ping":
        return rpc_result(id_, {})
    if method == "tools/list":
        return rpc_result(id_, {"tools": mcp_tools()})
    if method == "tools/call":
        if params.get("name") not in {t["name"] for t in mcp_tools()}:
            return rpc_error(id_, -32602, f"Unknown tool: {params.get('name')}")
        return rpc_result(id_, call_tool(db, request, params, lang))
    return rpc_error(id_, -32601, f"Method not found: {method}")


@router.post("/mcp")
async def mcp_post(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_lang)):
    if not origin_allowed(request):
        return JSONResponse(rpc_error(None, -32000, "Origin not allowed"), status_code=403)
    try:
        msg = await request.json()
    except Exception:
        return JSONResponse(rpc_error(None, -32700, "Parse error"), status_code=400)
    if isinstance(msg, list):  # JSON-RPC batch (allowed by protocol 2025-03-26)
        replies = [r for r in (handle(db, request, m, lang) for m in msg) if r is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = handle(db, request, msg, lang)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.get("/mcp")
def mcp_get():
    # This server does not open a server-to-client SSE stream; clients use POST only.
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
def mcp_delete():
    return Response(status_code=405, headers={"Allow": "POST"})


@router.get("/api/mcp/tools")
def mcp_tool_list():
    return {"enabled": True, "endpoint": "/mcp", "transport": "streamable-http", "tools": mcp_tools()}
