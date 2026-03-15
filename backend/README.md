# ReviewPro Backend

FastAPI backend for PDF/image document audit with:

- strategy management
- document upload + page index extraction
- queued audit jobs with progress
- DashScope BaiLian OpenAI-compatible integration (optional) + deterministic local fallback
- SQLite persistence

## 1) Install

```powershell
cd backend
$env:HTTP_PROXY=''
$env:HTTPS_PROXY=''
$env:ALL_PROXY=''
$env:NO_PROXY='*'
$env:PIP_INDEX_URL='http://pypi.tuna.tsinghua.edu.cn/simple'
$env:PIP_TRUSTED_HOST='pypi.tuna.tsinghua.edu.cn'
python -m pip install -r requirements.txt
```

## 2) Configure (optional)

Create `.env` in `backend` from `.env.example`:

```env
REVIEWPRO_DATABASE_URL=sqlite:///./storage/reviewpro.db
REVIEWPRO_STORAGE_DIR=storage
REVIEWPRO_LOG_LEVEL=INFO
REVIEWPRO_LLM_API_KEY=
REVIEWPRO_LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
REVIEWPRO_LLM_MODEL=qwen3.5-plus
```

```powershell
Copy-Item .env.example .env
```

If `REVIEWPRO_LLM_API_KEY` is empty, backend uses local deterministic auditing.
Set `REVIEWPRO_LOG_LEVEL=DEBUG` when you want more verbose backend logs.

## 3) Start

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API base URL:

`http://127.0.0.1:8000/api`

## 4) Test

```powershell
cd backend
python -m pytest -q
```
