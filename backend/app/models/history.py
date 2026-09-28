from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    feedback = relationship(
        "QueryFeedback", back_populates="history", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def feedback_rating(self):
        return self.feedback.rating if self.feedback else None


class QueryFeedback(Base):
    __tablename__ = "query_feedback"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("query_history.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    rating = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    history = relationship("QueryHistory", back_populates="feedback")
