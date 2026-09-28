import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from qdrant_client import models
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.documents import Document
from app.models.history import QueryFeedback, QueryHistory
from app.models.rbac import User
from app.models.sharing import DocumentGrant
from app.schemas.rag import DocumentOut, FeedbackOut, FeedbackRequest, QueryHistoryOut, QueryRequest, QueryResponse
from app.services.auditing import record_audit
from app.services.ingestion import index_document
from app.services.qa import answer_question
from app.services.tagging import normalize_tag, parse_tags
from app.services.vector_store import COLLECTION_NAME, get_qdrant

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents and RAG"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def document_response(document: Document, user: User) -> dict:
    is_admin = user.role.name.casefold() == "admin"
    shared = not is_admin and document.owner_id != user.id
    data = DocumentOut.model_validate(document).model_dump()
    data.update({
        "shared": shared,
        "can_delete": is_admin or document.owner_id == user.id,
        "owner_username": document.owner.username if shared else None,
    })
    return data


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile, db: DbSession, user: CurrentUser, tags: str = Form(default="")):
    try:
        content = file.file.read(settings.max_upload_bytes + 1)
        document = index_document(
            filename=file.filename or "upload", content=content, owner=user, db=db, tags=parse_tags(tags),
        )
        record_audit(db, actor=user, event_type="document.uploaded", document_id=document.id,
                     summary=f"Document uploaded: {document.original_filename}")
        db.commit()
        return document_response(document, user)
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Document indexing failed")
        raise HTTPException(status_code=503, detail="Document indexing failed; check local embedding and Qdrant services") from error
    finally:
        file.file.close()


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: DbSession, user: CurrentUser, tag: str | None = Query(default=None)):
    is_admin = user.role.name.casefold() == "admin"
    query = db.query(Document)
    if not is_admin:
        granted_ids = [row[0] for row in db.query(DocumentGrant.document_id)
                       .filter(DocumentGrant.user_id == user.id).all()]
        ownership = [Document.owner_id == user.id]
        if granted_ids:
            ownership.append(Document.id.in_(granted_ids))
        query = query.filter(or_(*ownership))
    documents = query.order_by(Document.created_at.desc()).all()
    if tag:
        try:
            wanted_tag = normalize_tag(tag)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        documents = [document for document in documents if wanted_tag in document.tags]
    return [document_response(document, user) for document in documents]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: DbSession, user: CurrentUser):
    query = db.query(Document).filter(Document.id == document_id)
    if user.role.name.casefold() != "admin":
        query = query.filter(Document.owner_id == user.id)
    document = query.first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        get_qdrant().delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document.id)),
            ])),
            wait=True,
        )
    except Exception as error:
        logger.exception("Qdrant deletion failed for document %s", document_id)
        raise HTTPException(status_code=503, detail="Could not remove document vectors") from error
    Path(document.storage_path).unlink(missing_ok=True)
    record_audit(db, actor=user, event_type="document.deleted", document_id=document.id,
                 summary=f"Document deleted: {document.original_filename}")
    db.delete(document)
    db.commit()


@router.post("/rag/query", response_model=QueryResponse)
def query_documents(payload: QueryRequest, user: CurrentUser, db: DbSession):
    try:
        shared_ids = []
        if user.role.name.casefold() != "admin":
            shared_ids = [row[0] for row in db.query(DocumentGrant.document_id)
                          .filter(DocumentGrant.user_id == user.id).all()]
        result = answer_question(payload.question, user, tag=payload.tag, shared_document_ids=shared_ids)
        history_entry = QueryHistory(
            user_id=user.id, question=payload.question,
            answer=result["answer"], sources=result["sources"],
        )
        db.add(history_entry)
        db.flush()
        stale = (db.query(QueryHistory.id)
                 .filter(QueryHistory.user_id == user.id)
                 .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
                 .offset(50).subquery())
        db.query(QueryHistory).filter(QueryHistory.id.in_(stale)).delete(synchronize_session=False)
        db.commit()
        return {**result, "history_id": history_entry.id, "feedback_rating": None}
    except Exception as error:
        db.rollback()
        logger.exception("RAG query or history save failed")
        raise HTTPException(status_code=503, detail="RAG service is unavailable; check the local embedding model, Ollama, and database") from error


@router.get("/rag/history", response_model=list[QueryHistoryOut])
def list_query_history(db: DbSession, user: CurrentUser):
    return (db.query(QueryHistory).options(joinedload(QueryHistory.feedback))
            .filter(QueryHistory.user_id == user.id)
            .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
            .limit(50).all())


@router.put("/rag/history/{history_id}/feedback", response_model=FeedbackOut)
def rate_query(history_id: int, payload: FeedbackRequest, db: DbSession, user: CurrentUser):
    entry = db.query(QueryHistory).filter(
        QueryHistory.id == history_id, QueryHistory.user_id == user.id,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    if entry.feedback is None:
        entry.feedback = QueryFeedback(rating=payload.rating)
    else:
        entry.feedback.rating = payload.rating
    db.commit()
    return {"rating": entry.feedback.rating}


@router.delete("/rag/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_query_history(db: DbSession, user: CurrentUser):
    db.query(QueryHistory).filter(QueryHistory.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
