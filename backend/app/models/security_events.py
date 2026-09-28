from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_key_failed_at", "attempt_key", "failed_at"),)

    id = Column(Integer, primary_key=True)
    attempt_key = Column(String(64), nullable=False)
    failed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
