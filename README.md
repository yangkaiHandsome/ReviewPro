# ReviewPro

ReviewPro is a desktop-first AI document review system for technical files such as specifications, SOR documents, scanned PDFs, and drawing-like pages.

It combines a WPF client with a FastAPI backend to provide strategy-based document review, page preview, page-level annotation, asynchronous audit jobs, and optional LLM-assisted analysis.

## Overview

The project is designed around one practical goal: make document review traceable, visual, and repeatable.

Instead of treating a PDF as a single opaque file, ReviewPro turns it into a page-indexed review target:

- define reusable review strategies and rules
- upload PDF or image documents
- extract page metadata and text blocks
- build a page review plan under a review budget
- run asynchronous audits
- show page-level findings with bounding boxes in the desktop UI

If an LLM API key is configured, the backend can call a Kimi-compatible endpoint for structured audit output. If not, the system falls back to deterministic local heuristic auditing.

## Key Features

- Strategy management: create, edit, delete, and reuse structured review strategies
- Document ingestion: support for `PDF`, `PNG`, `JPG`, `JPEG`, `BMP`, `TIF`, `TIFF`
- Page analysis: detect text-heavy vs image-heavy pages and generate page previews
- Budgeted review planning: select representative pages instead of blindly reviewing every page
- Async audit workflow: submit jobs, poll progress, retry failed or incomplete runs
- Visual review UI: browse documents, inspect pages, zoom, and jump from findings to page annotations
- Local-first persistence: SQLite-based backend storage with no external infrastructure requirement
- Optional LLM integration: use remote model review when configured, or local heuristic review otherwise

## Architecture

### Frontend

- Framework: `WPF` on `.NET 8`
- Location: `ReviewPro/ReviewPro`
- Responsibility:
  - strategy editing
  - document list and preview
  - audit job submission and progress polling
  - bounding-box visualization for findings
  - backend endpoint configuration

### Backend

- Framework: `FastAPI`
- Location: `backend`
- Responsibility:
  - strategy and document APIs
  - file upload and page index generation
  - text block extraction and page rendering
  - audit queue processing
  - review plan generation
  - result persistence and retrieval

### Storage

- Database: `SQLite`
- Uploaded files: `backend/storage/uploads`
- Page index cache: `backend/storage/page_index`

## How It Works

1. A review strategy is created in the desktop client.
2. A document is uploaded to the backend.
3. The backend analyzes the file and builds page metadata:
   - page count
   - text preview
   - image density
   - likely table-of-contents signal
   - likely drawing/image-heavy signal
4. A review plan is generated with a page budget, so the system can review representative pages instead of always scanning the full document.
5. The audit worker pulls the job from the queue.
6. The backend gathers page payloads:
   - text blocks for text-oriented pages
   - image mode for drawing-like or image-heavy pages
7. The backend runs either:
   - Kimi-compatible LLM audit, or
   - local heuristic fallback
8. Structured findings are saved and shown in the WPF client with page-level highlights.

## Repository Layout

```text
.
|-- README.md
|-- ReviewPro/
|   |-- ReviewPro.sln
|   |-- ReviewPro/
|       |-- App.xaml
|       |-- MainWindow.xaml
|       |-- Models/
|       |-- Services/
|       `-- ReviewPro.csproj
`-- backend/
    |-- app/
    |   |-- api/
    |   |-- services/
    |   |-- config.py
    |   `-- main.py
    |-- tests/
    |-- requirements.txt
    |-- Dockerfile
    `-- docker-compose.yml
```

## Tech Stack

- Desktop UI: `WPF`, `C#`, `.NET 8`
- Backend API: `FastAPI`, `Python`
- Database: `SQLite`, `SQLAlchemy`
- PDF processing: `PyMuPDF`
- Image handling: `Pillow`
- HTTP client: `httpx`
- Testing: `pytest`

## Requirements

- Windows for the WPF frontend
- `.NET SDK 8.0+`
- `Python 3.10+`

## Quick Start

### 1. Start the backend

```powershell
cd backend
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend API base URL:

`http://127.0.0.1:8000/api`

### 2. Start the desktop client

```powershell
cd ReviewPro
dotnet run --project .\ReviewPro\ReviewPro.csproj
```

### 3. Use the app

1. Open the client.
2. Confirm the backend endpoint is `http://127.0.0.1:8000/api`.
3. Create or edit a review strategy.
4. Upload a document.
5. Run an audit and inspect the generated findings.

## Configuration

The backend reads configuration from `backend/.env` with the `REVIEWPRO_` prefix.

Example:

```env
REVIEWPRO_DATABASE_URL=sqlite:///./storage/reviewpro.db
REVIEWPRO_STORAGE_DIR=storage
REVIEWPRO_LOG_LEVEL=INFO
REVIEWPRO_LLM_API_KEY=
REVIEWPRO_LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
REVIEWPRO_LLM_MODEL=qwen3.5-plus
REVIEWPRO_MAX_PAGE_BUDGET=20
REVIEWPRO_MAX_PAGE_BUDGET_RATIO=0.3
REVIEWPRO_MIN_REVIEW_PAGES=4
REVIEWPRO_MAX_PREVIEW_CHARS=800
```

Notes:

- Leave `REVIEWPRO_LLM_API_KEY` empty to use the built-in heuristic fallback path.
- `REVIEWPRO_MAX_PAGE_BUDGET` and related settings control how many pages are selected for review.
- The WPF client stores the backend URL under the current user's local app data directory.
- Start from [`backend/.env.example`](E:\Workspace\ReviewPro\backend\.env.example) instead of editing tracked files directly.

## API Summary

Main backend endpoints:

- `GET /api/health`
- `GET /api/strategies`
- `POST /api/strategies`
- `PUT /api/strategies/{strategy_id}`
- `DELETE /api/strategies/{strategy_id}`
- `GET /api/documents`
- `POST /api/documents/upload`
- `GET /api/documents/{doc_id}/pages`
- `GET /api/documents/{doc_id}/search-pages`
- `GET /api/documents/{doc_id}/page/{page_number}/text-blocks`
- `GET /api/documents/{doc_id}/page/{page_number}/image`
- `DELETE /api/documents/{doc_id}`
- `POST /api/audit`
- `GET /api/audit/job/{job_id}`
- `GET /api/audit/{doc_id}`
- `POST /api/audit/{doc_id}/retry`

## Current Behavior and Design Choices

- The system is optimized for review workflows, not document editing.
- Audit jobs are asynchronous and processed by a background worker thread.
- Review planning is budget-based to control cost and latency on long documents.
- Text-heavy pages prefer text-block review for more precise annotations.
- Image-heavy pages prefer image mode for better compatibility with scanned files and drawings.
- The backend seeds one default strategy on first startup.

## Development

### Build the frontend

```powershell
dotnet build ReviewPro\ReviewPro.sln
```

### Run backend tests

```powershell
cd backend
python -m pytest -q
```

At the time of writing, the current local verification status is:

- frontend build: success
- backend tests: `8 passed`

## Community Files

- License: [LICENSE](E:\Workspace\ReviewPro\LICENSE)
- Contribution guide: [CONTRIBUTING.md](E:\Workspace\ReviewPro\CONTRIBUTING.md)
- Security policy: [SECURITY.md](E:\Workspace\ReviewPro\SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](E:\Workspace\ReviewPro\CODE_OF_CONDUCT.md)
- CI workflow: [.github/workflows/ci.yml](E:\Workspace\ReviewPro\.github\workflows\ci.yml)

## Limitations

- The desktop client currently targets Windows because it is built with WPF.
- The project does not provide online multi-user collaboration.
- Review quality depends on document type, rule quality, and whether an external LLM is configured.
- Drawing/image-heavy documents are supported, but precise semantic understanding is still harder than text-native PDFs.

## Roadmap Ideas

- richer rule schema and rule templates
- exportable review reports
- better OCR support for scanned documents
- more review-plan heuristics and model-driven page routing
- containerized full-stack startup flow

## License

This project is released under the [MIT License](E:\Workspace\ReviewPro\LICENSE).
