from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.models.rbac import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[Session, Depends(get_db)]) -> User:
    from app.auth.security import decode_access_token
    payload = decode_access_token(token)
    try:
        user_id = int(payload["sub"]) if payload else None
    except (TypeError, ValueError, KeyError):
        user_id = None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    user = db.query(User).options(joinedload(User.role)).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


def require_roles(*role_names: str):
    allowed = {name.casefold() for name in role_names}
    def role_dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role.name.casefold() not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_dependency
