import hashlib
import logging
import shutil
import uuid
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument
from llama_index.core.node_parser import SentenceSplitter
from qdrant_client import models

from app.core.config import settings
from app.models.document_tags import DocumentTag
from app.models.documents import Document
from app.models.rbac import User
from app.services.vector_store import BACKEND_DIR, COLLECTION_NAME, get_embedder, get_qdrant

logger = logging.getLogger(__name__)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        page_texts = []
        with pymupdf.open(path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()
                if settings.ocr_enabled and len(text) < 20 and page.get_images(full=True):
                    if not shutil.which("tesseract"):
                        raise ValueError(
                            "This PDF contains scanned pages. Install Tesseract OCR and add it to PATH, "
                            "then restart the backend and upload the PDF again."
                        )
                    try:
                        text_page = page.get_textpage_ocr(
                            language=settings.ocr_language, dpi=settings.ocr_dpi, full=True,
                        )
                        scanned_text = page.get_text("text", textpage=text_page).strip()
                        if scanned_text:
                            text = scanned_text
                    except Exception as error:
                        raise ValueError(
                            f"OCR could not read PDF page {page_number}. Check the Tesseract installation and language data."
                        ) from error
                page_texts.append(text)
        return "\n\n".join(page_texts)
    if suffix == ".docx":
        doc = DocxDocument(path)
        parts = [paragraph.text for paragraph in doc.paragraphs]
        for table in doc.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="replace")


def index_document(*, filename: str, content: bytes, owner: User, db, tags: list[str] | None = None) -> Document:
    safe_name = Path(filename.replace("\\", "/")).name[:255]
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF, DOCX, TXT, and MD files are supported")
    if len(content) > settings.max_upload_bytes:
        raise ValueError(f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit")
    if not content:
        raise ValueError("The uploaded file is empty")

    digest = hashlib.sha256(content).hexdigest()
    duplicate = db.query(Document).filter(Document.owner_id == owner.id, Document.sha256 == digest).first()
    if duplicate:
        raise FileExistsError("You have already uploaded this file")

    user_dir = BACKEND_DIR / "data" / "uploads" / str(owner.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    doc = None
    try:
        text = extract_text(path).strip()
        if not text:
            raise ValueError("No readable text was found in the file")
        doc = Document(original_filename=safe_name, storage_path=str(path), sha256=digest,
                       status="indexing", chunk_count=0, owner_id=owner.id)
        doc.tag_record = DocumentTag(tags=tags or [])
        db.add(doc)
        db.flush()

        splitter = SentenceSplitter(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
        chunks = [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
        if not chunks:
            raise ValueError("The file did not produce any indexable text")
        vectors = get_embedder().get_text_embedding_batch(chunks)
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()), vector=vector,
                payload={"owner_id": owner.id, "document_id": doc.id,
                         "filename": safe_name, "chunk_index": index, "text": chunk, "tags": tags or []},
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        get_qdrant().upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
        doc.status, doc.chunk_count = "ready", len(chunks)
        db.commit()
        db.refresh(doc)
        return doc
    except Exception:
        db.rollback()
        if doc is not None:
            try:
                get_qdrant().delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=models.FilterSelector(filter=models.Filter(must=[
                        models.FieldCondition(key="document_id", match=models.MatchValue(value=doc.id)),
                    ])),
                    wait=True,
                )
            except Exception:
                logger.exception("Failed to clean up vectors for incomplete document %s", doc.id)
        path.unlink(missing_ok=True)
        raise
