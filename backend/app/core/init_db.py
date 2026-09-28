from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.models.audit import AuditEvent
from app.models.documents import Document
from app.models.document_tags import DocumentTag
from app.models.history import QueryFeedback, QueryHistory
from app.models.rbac import Role, User
from app.models.security_events import LoginAttempt
from app.models.sharing import DocumentGrant, DocumentShare

DEFAULT_ROLES = {
    "user": "Standard authenticated user",
    "admin": "Administrator with user and role management access",
}


def init_db():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        for name, description in DEFAULT_ROLES.items():
            if db.query(Role).filter(Role.name == name).first() is None:
                db.add(Role(name=name, description=description))
        db.commit()

        if settings.initial_admin_username and settings.initial_admin_email and settings.initial_admin_password:
            if len(settings.initial_admin_password) < 12:
                raise ValueError("INITIAL_ADMIN_PASSWORD must be at least 12 characters")
            user = db.query(User).filter(
                (User.username == settings.initial_admin_username)
                | (User.email == settings.initial_admin_email.lower())
            ).first()
            if user is None:
                admin_role = db.query(Role).filter(Role.name == "admin").one()
                db.add(User(
                    username=settings.initial_admin_username,
                    email=settings.initial_admin_email.lower(),
                    hashed_password=hash_password(settings.initial_admin_password),
                    role=admin_role,
                ))
                db.commit()
    finally:
        db.close()
