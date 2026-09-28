import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.documents import Document
from app.models.rbac import User
from app.models.sharing import DocumentGrant, DocumentShare
from app.services.auditing import record_audit
from app.schemas.sharing import RedeemShareOut, RedeemShareRequest, ShareCreateOut, ShareListOut, ShareStatusOut

router = APIRouter(tags=["document sharing"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def manageable_document(document_id: int, db: Session, user: User) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.owner_id != user.id and user.role.name.casefold() != "admin":
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/documents/{document_id}/shares", response_model=ShareCreateOut, status_code=status.HTTP_201_CREATED)
def create_share(document_id: int, db: DbSession, user: CurrentUser):
    document = manageable_document(document_id, db, user)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    share = DocumentShare(
        document_id=document.id,
        created_by_user_id=user.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=expires_at,
    )
    db.add(share)
    record_audit(db, actor=user, event_type="share.created", document_id=document.id,
                 summary=f"One-time share key created for {document.original_filename}")
    db.commit()
    db.refresh(share)
    return {"share_id": share.id, "token": token, "expires_at": share.expires_at}


@router.get("/documents/{document_id}/shares", response_model=ShareListOut)
def list_shares(document_id: int, db: DbSession, user: CurrentUser):
    document = manageable_document(document_id, db, user)
    shares = (db.query(DocumentShare)
              .filter(DocumentShare.document_id == document.id)
              .order_by(DocumentShare.created_at.desc(), DocumentShare.id.desc()).all())
    redeemed_ids = [share.redeemed_by_user_id for share in shares if share.redeemed_by_user_id]
    usernames = {}
    if redeemed_ids:
        usernames = {entry.id: entry.username for entry in db.query(User).filter(User.id.in_(redeemed_ids)).all()}
    return {
        "document_id": document.id,
        "shares": [ShareStatusOut(
            share_id=share.id,
            expires_at=share.expires_at,
            redeemed_at=share.redeemed_at,
            redeemed_by_username=usernames.get(share.redeemed_by_user_id),
            revoked_at=share.revoked_at,
        ) for share in shares],
    }


@router.delete("/documents/{document_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(document_id: int, share_id: int, db: DbSession, user: CurrentUser):
    document = manageable_document(document_id, db, user)
    share = db.query(DocumentShare).filter(
        DocumentShare.id == share_id, DocumentShare.document_id == document.id,
    ).first()
    if share is None:
        raise HTTPException(status_code=404, detail="Share key not found")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(timezone.utc)
        db.query(DocumentGrant).filter(DocumentGrant.share_id == share.id).delete(synchronize_session=False)
        record_audit(db, actor=user, event_type="share.revoked", document_id=document.id,
                     target_user_id=share.redeemed_by_user_id,
                     summary=f"Document share revoked for {document.original_filename}")
        db.commit()


@router.post("/shares/redeem", response_model=RedeemShareOut)
def redeem_share(payload: RedeemShareRequest, db: DbSession, user: CurrentUser):
    token_hash = hashlib.sha256(payload.token.strip().encode("utf-8")).hexdigest()
    share = db.query(DocumentShare).filter(DocumentShare.token_hash == token_hash).first()
    now = datetime.now(timezone.utc)
    if share is None or share.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Share key is invalid, expired, or revoked")
    if share.redeemed_at is not None:
        raise HTTPException(status_code=409, detail="Share key has already been used")
    expires_at = share.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=404, detail="Share key is invalid, expired, or revoked")
    document = db.query(Document).filter(Document.id == share.document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Shared document is no longer available")
    if document.owner_id == user.id:
        raise HTTPException(status_code=409, detail="You already own this document")
    existing = db.query(DocumentGrant).filter(
        DocumentGrant.document_id == document.id, DocumentGrant.user_id == user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You already have access to this document")

    share.redeemed_by_user_id = user.id
    share.redeemed_at = now
    db.add(DocumentGrant(document_id=document.id, user_id=user.id, share_id=share.id))
    record_audit(db, actor=user, target_user_id=user.id, document_id=document.id,
                 event_type="share.redeemed", summary=f"Document share redeemed: {document.original_filename}")
    db.commit()
    return RedeemShareOut(
        document_id=document.id,
        filename=document.original_filename,
        owner_username=document.owner.username,
    )
