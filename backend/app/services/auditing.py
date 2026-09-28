from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.rbac import User


def record_audit(
    db: Session, *, actor: User | None, event_type: str, summary: str,
    target_user_id: int | None = None, document_id: int | None = None,
) -> None:
    """Add a minimal audit event to the current transaction; never include secrets or user content."""
    db.add(AuditEvent(
        actor_user_id=actor.id if actor else None,
        target_user_id=target_user_id,
        document_id=document_id,
        event_type=event_type,
        summary=summary[:255],
    ))
