from sqlalchemy import Column, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocumentTag(Base):
    __tablename__ = "document_tags"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tags = Column(JSON, nullable=False, default=list)
    document = relationship("Document", back_populates="tag_record")
