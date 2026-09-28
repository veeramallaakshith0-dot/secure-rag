from datetime import datetime

from pydantic import BaseModel


class AdminAuditEventOut(BaseModel):
    id: int
    event_type: str
    summary: str
    actor_username: str | None
    target_username: str | None
    document_id: int | None
    created_at: datetime
