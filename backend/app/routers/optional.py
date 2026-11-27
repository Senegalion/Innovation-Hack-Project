from fastapi import APIRouter

router = APIRouter(tags=["optional"])

NOT_ENABLED = {"enabled": False, "detail": "Reserved for a future release"}


@router.post("/api/assistant/ai")
def ai_assistant():
    return {**NOT_ENABLED, "feature": "AI assistant over documentation", "fallback": "/api/documents/search"}


@router.get("/api/notifications/inspections")
def inspection_notifications():
    return {**NOT_ENABLED, "feature": "Automatic inspection notifications", "items": []}


@router.get("/mcp")
@router.post("/mcp")
def mcp_endpoint():
    return {**NOT_ENABLED, "feature": "MCP server"}


@router.get("/api/mcp/tools")
def mcp_tools():
    return {**NOT_ENABLED, "feature": "MCP integration", "tools": []}


@router.post("/api/nfc/{tag_id}")
def nfc(tag_id: str):
    return {**NOT_ENABLED, "feature": "NFC proximity identification", "tag_id": tag_id,
            "fallback": f"/api/scan/{tag_id}"}
