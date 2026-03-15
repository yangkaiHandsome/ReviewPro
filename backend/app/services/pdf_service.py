from __future__ import annotations

import io
import json
import re
from pathlib import Path

import fitz
from PIL import Image
from fastapi import HTTPException, UploadFile, status

from app.config import get_settings
from app.schemas import PageMeta, PageTextBlock


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _normalize_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def _estimate_image_density(page: fitz.Page) -> float:
    area = max(page.rect.width * page.rect.height, 1.0)
    image_count = len(page.get_images(full=True))
    return round((image_count * 1_000_000.0) / area, 3)


def validate_upload_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename.",
        )
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext or 'unknown'}",
        )
    return ext


async def save_upload_file(doc_id: str, file: UploadFile) -> Path:
    settings = get_settings()
    extension = validate_upload_filename(file.filename or "")
    safe_name = Path(file.filename or "document").name
    target_path = (settings.upload_dir / f"{doc_id}_{safe_name}").resolve()

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    target_path.write_bytes(content)

    if extension in PDF_EXTENSIONS:
        return target_path

    # Keep image files as-is. Each image is treated as a single-page document.
    return target_path


def _is_toc_like(text_preview: str) -> bool:
    if not text_preview:
        return False
    lower = text_preview.lower()
    toc_markers = ["鐩綍", "contents", "table of contents", "绔犺妭", "chapter"]
    return any(marker in lower for marker in toc_markers)


def _is_likely_drawing(has_text: bool, image_density: float) -> bool:
    return (not has_text) or image_density > 8.0


def analyze_document(document_path: Path, max_preview_chars: int) -> tuple[int, str, list[PageMeta]]:
    document_path = ensure_document_path(document_path)
    ext = document_path.suffix.lower()
    if ext in PDF_EXTENSIONS:
        return _analyze_pdf(document_path, max_preview_chars)
    return _analyze_image(document_path)


def resolve_document_path(document_path: Path | str) -> Path:
    raw_path = Path(document_path)
    candidates: list[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append((Path.cwd() / raw_path).resolve())
        candidates.append((BACKEND_ROOT / raw_path).resolve())

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0] if candidates else raw_path.resolve()


def ensure_document_path(document_path: Path | str) -> Path:
    resolved = resolve_document_path(document_path)
    if not resolved.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found. Remove it from the list and upload it again if needed.",
        )
    return resolved


def _analyze_pdf(document_path: Path, max_preview_chars: int) -> tuple[int, str, list[PageMeta]]:
    try:
        doc = fitz.open(document_path)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read PDF document: {exc}",
        ) from exc
    try:
        pages: list[PageMeta] = []
        text_pages = 0
        for idx in range(doc.page_count):
            page = doc[idx]
            text = _normalize_text(page.get_text("text"))
            has_text = bool(text)
            if has_text:
                text_pages += 1
            preview = text[:max_preview_chars]
            image_density = _estimate_image_density(page)
            pages.append(
                PageMeta(
                    page_number=idx + 1,
                    has_text=has_text,
                    text_preview=preview,
                    image_density=image_density,
                    page_width=float(page.rect.width),
                    page_height=float(page.rect.height),
                    is_toc_like=_is_toc_like(preview),
                    likely_drawing=_is_likely_drawing(has_text, image_density),
                )
            )

        doc_type = "text" if doc.page_count == 0 or text_pages / doc.page_count >= 0.5 else "image"
        return doc.page_count, doc_type, pages
    finally:
        doc.close()


def _analyze_image(document_path: Path) -> tuple[int, str, list[PageMeta]]:
    try:
        with Image.open(document_path) as image:
            width, height = image.size
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read image document: {exc}",
        ) from exc
    page = PageMeta(
        page_number=1,
        has_text=False,
        text_preview="",
        image_density=20.0,
        page_width=float(width),
        page_height=float(height),
        is_toc_like=False,
        likely_drawing=True,
    )
    return 1, "image", [page]


def write_page_index(doc_id: str, pages: list[PageMeta]) -> None:
    settings = get_settings()
    index_path = (settings.page_index_dir / f"{doc_id}.json").resolve()
    index_path.write_text(
        json.dumps([page.model_dump() for page in pages], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_page_index(doc_id: str) -> list[PageMeta]:
    settings = get_settings()
    index_path = (settings.page_index_dir / f"{doc_id}.json").resolve()
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return [PageMeta.model_validate(item) for item in data]


def delete_page_index(doc_id: str) -> None:
    settings = get_settings()
    index_path = (settings.page_index_dir / f"{doc_id}.json").resolve()
    if index_path.exists():
        index_path.unlink()


def get_page_text_blocks(document_path: Path, page_number: int) -> list[PageTextBlock]:
    document_path = ensure_document_path(document_path)
    if document_path.suffix.lower() not in PDF_EXTENSIONS:
        return []

    try:
        doc = fitz.open(document_path)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read PDF document: {exc}",
        ) from exc
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page {page_number} out of range.",
            )
        page = doc[page_number - 1]
        blocks: list[PageTextBlock] = []
        for block in page.get_text("blocks"):
            text = _normalize_text(block[4] if len(block) > 4 else "")
            if not text:
                continue
            blocks.append(
                PageTextBlock(
                    text=text,
                    bbox=[
                        float(block[0]),
                        float(block[1]),
                        float(block[2]),
                        float(block[3]),
                    ],
                )
            )
        return blocks
    finally:
        doc.close()


def render_page_image(document_path: Path, page_number: int, dpi: int = 150) -> bytes:
    document_path = ensure_document_path(document_path)
    if document_path.suffix.lower() in PDF_EXTENSIONS:
        try:
            doc = fitz.open(document_path)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to read PDF document: {exc}",
            ) from exc
        try:
            if page_number < 1 or page_number > doc.page_count:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Page {page_number} out of range.",
                )
            page = doc[page_number - 1]
            scale = max(72, dpi) / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return pix.tobytes("png")
        finally:
            doc.close()

    if page_number != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_number} out of range.",
        )
    try:
        with Image.open(document_path) as image:
            output = io.BytesIO()
            image.convert("RGB").save(output, format="PNG")
            return output.getvalue()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read image document: {exc}",
        ) from exc


