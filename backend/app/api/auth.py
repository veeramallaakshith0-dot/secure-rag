import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user, require_roles
from app.auth.security import create_access_token, hash_password, verify_password
from app.core.database import get_db
from app.models.audit import AuditEvent
from app.models.history import QueryHistory
from app.models.rbac import Role, User
from app.models.security_events import LoginAttempt
from app.schemas.audit import AdminAuditEventOut
from app.schemas.auth import ActiveUpdate, RegisterRequest, RoleUpdate, TokenOut, UserOut
from app.schemas.rag import AdminQueryHistoryOut
from app.services.auditing import record_audit

router = APIRouter(prefix="/auth", tags=["authentication"])
DbSession = Annotated[Session, Depends(get_db)]

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession):
    if db.query(User).filter((User.username == payload.username) | (User.email == str(payload.email).lower())).first():
        raise HTTPException(status_code=409, detail="Username or email is already registered")
    role = db.query(Role).filter(Role.name == "user").first()
    if role is None:
        raise HTTPException(status_code=503, detail="Default role is not initialized")
    user = User(username=payload.username, email=str(payload.email).lower(), hashed_password=hash_password(payload.password), role=role)
    db.add(user)
    db.flush()
    record_audit(db, actor=user, target_user_id=user.id, event_type="account.registered", summary=f"Account registered: {user.username}")
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=TokenOut)
def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    client_ip = request.client.host if request.client else "unknown"
    identity = form.username.strip().casefold()
    attempt_key = hashlib.sha256(f"{client_ip}:{identity}".encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=15)
    attempts = (db.query(LoginAttempt)
                .filter(LoginAttempt.attempt_key == attempt_key, LoginAttempt.failed_at > cutoff)
                .order_by(LoginAttempt.failed_at.asc()).limit(5).all())
    if len(attempts) >= 5:
        retry_after = max(1, math.ceil((attempts[0].failed_at + timedelta(minutes=15) - now).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Try again after the temporary limit expires.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).options(joinedload(User.role)).filter(
        (User.username == form.username) | (User.email == form.username.lower())
    ).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        db.add(LoginAttempt(attempt_key=attempt_key))
        db.query(LoginAttempt).filter(LoginAttempt.failed_at < now - timedelta(days=1)).delete(synchronize_session=False)
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect username/email or password", headers={"WWW-Authenticate": "Bearer"})

    db.query(LoginAttempt).filter(LoginAttempt.attempt_key == attempt_key).delete(synchronize_session=False)
    db.commit()
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    record_audit(db, actor=user, target_user_id=user.id, event_type="auth.login", summary=f"Successful sign-in: {user.username}")
    db.commit()
    return TokenOut(access_token=create_access_token(str(user.id)))

@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user

@router.get("/users", response_model=list[UserOut])
def list_users(db: DbSession, _: Annotated[User, Depends(require_roles("admin"))]):
    return db.query(User).options(joinedload(User.role)).order_by(User.id).all()

@router.get("/users/{user_id}/history", response_model=list[AdminQueryHistoryOut])
def user_query_history(user_id: int, db: DbSession, _: Annotated[User, Depends(require_roles("admin"))]):
    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found")
    return (db.query(QueryHistory)
            .filter(QueryHistory.user_id == user_id)
            .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
            .limit(50).all())
@router.get("/audit", response_model=list[AdminAuditEventOut])
def list_audit_events(
    db: DbSession,
    _: Annotated[User, Depends(require_roles("admin"))],
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None, max_length=80),
):
    query = db.query(AuditEvent)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    events = query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).all()
    user_ids = {event.actor_user_id for event in events if event.actor_user_id}
    user_ids.update(event.target_user_id for event in events if event.target_user_id)
    usernames = {entry.id: entry.username for entry in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [AdminAuditEventOut(
        id=event.id, event_type=event.event_type, summary=event.summary,
        actor_username=usernames.get(event.actor_user_id),
        target_username=usernames.get(event.target_user_id), document_id=event.document_id,
        created_at=event.created_at,
    ) for event in events]


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(user_id: int, payload: RoleUpdate, db: DbSession, _: Annotated[User, Depends(require_roles("admin"))]):
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user_id).first()
    role = db.query(Role).filter(Role.name == payload.role.casefold()).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    previous_role = user.role.name
    user.role = role
    record_audit(db, actor=_, target_user_id=user.id, event_type="account.role_changed", summary=f"Role changed for {user.username}: {previous_role} -> {role.name}")
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_user_active(user_id: int, payload: ActiveUpdate, db: DbSession, admin: Annotated[User, Depends(require_roles("admin"))]):
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="Admins cannot deactivate their own account")
    user.is_active = payload.is_active
    state = "activated" if payload.is_active else "deactivated"
    record_audit(db, actor=admin, target_user_id=user.id, event_type=f"account.{state}", summary=f"Account {state}: {user.username}")
    db.commit()
    db.refresh(user)
    return user
