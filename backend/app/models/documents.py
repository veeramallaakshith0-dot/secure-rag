from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("owner_id", "sha256", name="uq_document_owner_sha256"),)

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(1024), nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="ready")
    chunk_count = Column(Integer, nullable=False, default=0)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User")
    tag_record = relationship(
        "DocumentTag", back_populates="document", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def tags(self):
        return self.tag_record.tags if self.tag_record else []
