from __future__ import annotations

import os
import time
from io import BytesIO

import fitz

from app.config import get_settings


def _make_sample_pdf() -> bytes:
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        "Glossary: API=Application Programming Interface\n"
        "Version History: v1.0\n"
        "This document is used for audit testing.",
    )
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Conclusion: support plan, progress and annotations.")
    data = doc.tobytes()
    doc.close()
    return data


def _create_strategy(client) -> str:
    payload = {
        "name": "Test Strategy",
        "rules": [
            {
                "id": "R001",
                "title": "Glossary",
                "description": "Document should contain glossary information",
                "severity": "high",
                "is_required": True,
            },
            {
                "id": "R002",
                "title": "Version History",
                "description": "Document should contain version history",
                "severity": "medium",
                "is_required": True,
            },
        ],
    }
    response = client.post("/api/strategies", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _upload_document(client) -> str:
    data = _make_sample_pdf()
    files = {"file": ("sample.pdf", BytesIO(data), "application/pdf")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201
    return response.json()["doc_id"]


def test_strategy_crud(client):
    strategy_id = _create_strategy(client)

    list_resp = client.get("/api/strategies")
    assert list_resp.status_code == 200
    assert any(item["id"] == strategy_id for item in list_resp.json())

    update_payload = {
        "name": "Test Strategy Updated",
        "rules": [
            {
                "id": "R009",
                "title": "Conclusion",
                "description": "Document should contain conclusion",
                "severity": "low",
                "is_required": False,
            }
        ],
    }
    update_resp = client.put(f"/api/strategies/{strategy_id}", json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Test Strategy Updated"
    assert len(update_resp.json()["rules"]) == 1


def test_can_create_multiple_strategies_with_same_rule_ids(client):
    first_strategy_id = _create_strategy(client)
    second_strategy_id = _create_strategy(client)

    assert first_strategy_id != second_strategy_id

    list_resp = client.get("/api/strategies")
    assert list_resp.status_code == 200
    strategy_ids = {item["id"] for item in list_resp.json()}
    assert first_strategy_id in strategy_ids
    assert second_strategy_id in strategy_ids


def test_upload_pages_and_image(client):
    doc_id = _upload_document(client)

    pages_resp = client.get(f"/api/documents/{doc_id}/pages")
    assert pages_resp.status_code == 200
    pages = pages_resp.json()
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1

    image_resp = client.get(f"/api/documents/{doc_id}/page/1/image")
    assert image_resp.status_code == 200
    assert image_resp.headers["content-type"] == "image/png"
    assert image_resp.content.startswith(b"\x89PNG")

    blocks_resp = client.get(f"/api/documents/{doc_id}/page/1/text-blocks")
    assert blocks_resp.status_code == 200
    assert len(blocks_resp.json()) >= 1


def test_missing_document_file_is_cleaned_from_list(client):
    doc_id = _upload_document(client)

    settings = get_settings()
    upload_path = next(settings.upload_dir.glob(f"{doc_id}_*"))
    os.remove(upload_path)

    pages_resp = client.get(f"/api/documents/{doc_id}/pages")
    assert pages_resp.status_code == 404
    assert "Document file not found" in pages_resp.json()["detail"]

    list_resp = client.get("/api/documents")
    assert list_resp.status_code == 200
    assert all(item["id"] != doc_id for item in list_resp.json())


def test_delete_document_removes_file_and_index(client):
    doc_id = _upload_document(client)

    settings = get_settings()
    upload_path = next(settings.upload_dir.glob(f"{doc_id}_*"))
    index_path = settings.page_index_dir / f"{doc_id}.json"

    delete_resp = client.delete(f"/api/documents/{doc_id}")
    assert delete_resp.status_code == 204
    assert not upload_path.exists()
    assert not index_path.exists()

    get_resp = client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 404


def test_audit_flow(client):
    strategy_id = _create_strategy(client)
    doc_id = _upload_document(client)

    submit_resp = client.post(
        "/api/audit",
        json={"doc_id": doc_id, "strategy_id": strategy_id},
    )
    assert submit_resp.status_code == 202
    job_id = submit_resp.json()["job_id"]

    last_status = None
    payload = None
    for _ in range(80):
        time.sleep(0.1)
        job_resp = client.get(f"/api/audit/job/{job_id}")
        assert job_resp.status_code == 200
        payload = job_resp.json()
        last_status = payload["status"]
        if last_status in {"completed", "failed"}:
            break

    assert payload is not None
    assert last_status == "completed", payload.get("error_message")
    assert payload["progress"] == 100.0
    assert len(payload["visited_pages"]) >= 1
    assert len(payload["results"]) >= 1

    latest_resp = client.get(f"/api/audit/{doc_id}")
    assert latest_resp.status_code == 200
    assert latest_resp.json()["job_id"] == job_id

    retry_resp = client.post(f"/api/audit/{doc_id}/retry")
    assert retry_resp.status_code == 202
