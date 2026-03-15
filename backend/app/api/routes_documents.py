from __future__ import annotations

import logging
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditJob, AuditResult, Document
from app.schemas import DocumentResponse, PageMeta, PageTextBlock, SearchPagesResponse, UploadResponse
from app.services.pdf_service import (
    analyze_document,
    delete_page_index,
    ensure_document_path,
    get_page_text_blocks,
    read_page_index,
    render_page_image,
    resolve_document_path,
    save_upload_file,
    write_page_index,
)


router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


def _delete_document_artifacts(document: Document) -> None:
    path = resolve_document_path(document.path)
    if path.exists():
        path.unlink()
    delete_page_index(document.id)


def _purge_document(db: Session, document: Document) -> None:
    logger.warning("Purging stale document. doc_id=%s filename=%s", document.id, document.filename)
    _delete_document_artifacts(document)
    db.execute(delete(AuditResult).where(AuditResult.doc_id == document.id))
    db.execute(delete(AuditJob).where(AuditJob.doc_id == document.id))
    db.delete(document)


@router.get("", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)) -> List[Document]:
    stmt = select(Document).order_by(Document.upload_time.desc())
    documents = list(db.scalars(stmt).all())
    valid_documents: list[Document] = []
    removed_stale = False
    for document in documents:
        if resolve_document_path(document.path).exists():
            valid_documents.append(document)
            continue
        _purge_document(db, document)
        removed_stale = True

    if removed_stale:
        db.commit()
        logger.info("Removed stale document records during document listing.")

    return valid_documents


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    settings = get_settings()
    doc_id = str(uuid4())
    logger.info(
        "Uploading document. doc_id=%s filename=%s content_type=%s",
        doc_id,
        file.filename,
        file.content_type,
    )
    path = await save_upload_file(doc_id, file)
    page_count, doc_type, pages = analyze_document(path, max_preview_chars=settings.max_preview_chars)
    write_page_index(doc_id, pages)

    document = Document(
        id=doc_id,
        filename=file.filename or path.name,
        path=str(path),
        mime_type=file.content_type or "application/octet-stream",
        page_count=page_count,
        doc_type=doc_type,
    )
    db.add(document)
    db.commit()
    logger.info(
        "Document uploaded successfully. doc_id=%s path=%s page_count=%s doc_type=%s",
        doc_id,
        path,
        page_count,
        doc_type,
    )

    return UploadResponse(
        doc_id=doc_id,
        filename=document.filename,
        page_count=page_count,
        doc_type=doc_type,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    ensure_document_path(document.path)
    return document


@router.get("/{doc_id}/pages", response_model=List[PageMeta])
def list_document_pages(doc_id: str, db: Session = Depends(get_db)) -> List[PageMeta]:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    path = ensure_document_path(document.path)
    pages = read_page_index(doc_id)
    if pages:
        logger.info("Returning cached page index. doc_id=%s page_count=%s", doc_id, len(pages))
        return pages

    settings = get_settings()
    page_count, doc_type, pages = analyze_document(path, max_preview_chars=settings.max_preview_chars)
    document.page_count = page_count
    document.doc_type = doc_type
    db.add(document)
    db.commit()
    write_page_index(doc_id, pages)
    logger.info("Generated page index. doc_id=%s page_count=%s doc_type=%s", doc_id, page_count, doc_type)
    return pages


@router.get("/{doc_id}/search-pages", response_model=SearchPagesResponse)
def search_pages(
    doc_id: str,
    query: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> SearchPagesResponse:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    pages = read_page_index(doc_id)
    query_lower = query.lower()
    matches = [page.page_number for page in pages if query_lower in page.text_preview.lower()]
    return SearchPagesResponse(pages=matches)


@router.get("/{doc_id}/page/{page_number}/text-blocks", response_model=List[PageTextBlock])
def get_page_blocks(doc_id: str, page_number: int, db: Session = Depends(get_db)) -> List[PageTextBlock]:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    blocks = get_page_text_blocks(ensure_document_path(document.path), page_number)
    logger.info("Returning text blocks. doc_id=%s page=%s block_count=%s", doc_id, page_number, len(blocks))
    return blocks


@router.get("/{doc_id}/page/{page_number}/image")
def get_page_image(
    doc_id: str,
    page_number: int,
    dpi: int = Query(default=150, ge=72, le=300),
    db: Session = Depends(get_db),
) -> Response:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    content = render_page_image(ensure_document_path(document.path), page_number, dpi=dpi)
    logger.info("Rendered page image. doc_id=%s page=%s dpi=%s bytes=%s", doc_id, page_number, dpi, len(content))
    return Response(content=content, media_type="image/png")


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, db: Session = Depends(get_db)) -> Response:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    _purge_document(db, document)
    db.commit()
    logger.info("Deleted document. doc_id=%s filename=%s", document.id, document.filename)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
