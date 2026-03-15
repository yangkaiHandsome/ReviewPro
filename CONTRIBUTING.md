# Contributing

Thanks for contributing to ReviewPro.

## Development Setup

### Backend

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd ReviewPro
dotnet build .\ReviewPro.sln
dotnet run --project .\ReviewPro\ReviewPro.csproj
```

## Before Opening a Pull Request

- keep changes focused and reviewable
- avoid committing secrets, local databases, or generated files
- update documentation when behavior changes
- run the backend tests
- ensure the WPF client still builds

## Validation Commands

```powershell
cd backend
python -m pytest -q
```

```powershell
dotnet build ReviewPro\ReviewPro.sln
```

## Commit Guidance

- use clear commit messages
- separate refactors from behavior changes when possible
- include context for architectural or API changes

## Pull Request Checklist

- I removed secrets and local-only configuration
- I updated docs if needed
- I ran tests relevant to the change
- I noted any known gaps or follow-up work
