from fastapi import APIRouter

router = APIRouter(tags=["optional"])

NOT_ENABLED = {"enabled": False, "detail": "Reserved for a future release"}


@router.get("/api/notifications/inspections")
def inspection_notifications():
    return {**NOT_ENABLED, "feature": "Automatic inspection notifications", "items": []}


@router.post("/api/nfc/{tag_id}")
def nfc(tag_id: str):
    return {**NOT_ENABLED, "feature": "NFC proximity identification", "tag_id": tag_id,
            "fallback": f"/api/scan/{tag_id}"}
