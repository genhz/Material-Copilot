# Material Sandbox Backend

FastAPI backend for Material Copilot. It provides material search, AI chat,
crystal-structure substitution, and asynchronous MatterGen generation APIs.

## Environment

This backend uses the existing MatterGen Python 3.10 environment:

```text
../mattergen/.venv
```

Do not create `backend/.venv` and do not run `uv sync --reinstall`.

Install or update only the backend dependencies:

```bash
source ../mattergen/.venv/bin/activate
uv sync --active --inexact
```

## Run

```bash
../mattergen/.venv/bin/python -m uvicorn main:app \
  --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
../mattergen/.venv/bin/python -m pytest
```

MatterGen generation runs in a separate `generation.worker` process. The local
checkpoint is expected at:

```text
../mattergen/checkpoints/dft_mag_density
```

See the repository root `README.md` for full setup and configuration details.
