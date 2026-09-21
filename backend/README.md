# Material Sandbox Backend

FastAPI backend for Material Copilot. It provides material search, AI chat,
crystal-structure substitution, and asynchronous MatterGen generation APIs.

## Environment

This backend uses the existing MatterGen Python 3.10 environment:

```text
.venv
```

The MatterGen source and local checkpoints are bundled under `backend/vendor/mattergen/`.
Do not run `uv sync --reinstall`.

Install or update only the backend dependencies:

```bash
uv sync
```

## Run

```bash
.venv/bin/python -m uvicorn main:app \
  --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
.venv/bin/python -m pytest
```

MatterGen generation runs in a separate `generation.worker` process. The local
checkpoint is expected at:

```text
vendor/mattergen/checkpoints/dft_mag_density
```

See the repository root `README.md` for full setup and configuration details.
