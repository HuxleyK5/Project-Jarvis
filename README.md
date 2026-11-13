# JARVIS

Personal AI assistant project built incrementally. Current scope: Phase 1 local FastAPI backend and independent frontend scaffold. AI, speech, automation, persistence, and integrations are not implemented.

This repository is the JARVIS root; no nested JARVIS directory is needed.

## Directory guide

| Directory | Purpose |
| --- | --- |
| backend/ | Independent Python backend package |
| backend/core/ | Future coordination and shared contracts |
| backend/voice/ | Future audio and speech adapters |
| backend/memory/ | Future persistence interfaces and implementations |
| backend/automation/ | Future user-authorized action workflows |
| backend/tools/ | Future narrowly scoped assistant capabilities |
| backend/integrations/ | Future model runtime and external service adapters |
| backend/tests/ | Backend tests |
| frontend/ | Independent React, TypeScript, and Vite project |
| frontend/src/components/ | Reusable UI elements |
| frontend/src/pages/ | Page-level views |
| frontend/src/services/ | Future backend communication adapters |
| frontend/src/hooks/ | Reusable React hooks |
| frontend/src/styles/ | Shared CSS |
| data/ | Local runtime data, ignored by Git except its placeholder |
| docs/ | Hardware report, architecture, and roadmap |
| scripts/ | Future development helpers |

## Compatibility

See [hardware report](docs/HARDWARE_REPORT.md). Python 3.12.4 and Node.js 20.16.0 are installed. [Vite 6 supports Node.js 20](https://v6.vite.dev/guide/); [newer Vite requires Node.js 20.19+ or 22.12+](https://vite.dev/guide/). Vite 6 is selected to accommodate the installed runtime. Reassess versions before approved installation.

With approximately 16 GiB RAM and 6 GiB VRAM, keep dependencies small. No GPU libraries, models, or mandatory paid APIs are included. Future small quantized model experiments should follow the hardware report.

## Configuration

Backend settings come from process environment variables. Defaults: `JARVIS_HOST=127.0.0.1`, `JARVIS_PORT=8000`, and `JARVIS_LOG_LEVEL=info`. Only `127.0.0.1`, `::1`, or `localhost` are accepted hosts. Invalid configuration fails startup. Root `.env.example` documents these values; environment files are not automatically loaded. Frontend configuration remains separate. Local environment files are ignored.

Never commit passwords, tokens, API keys, or private keys. All `VITE_` values are public browser configuration and must never contain secrets.

## Run and verify

The backend dependencies are installed in the approved project-local `.venv`. For a fresh checkout, obtain installation approval first, then use Python 3.12 from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/tests/requirements.txt
```

For runtime-only dependencies use `-r requirements.txt`. HTTPX is test-only. No environment activation or execution-policy change is needed.

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m backend.main
```

The server binds to `127.0.0.1:8000`. Stop it with Ctrl+C. To choose another local port, set `$env:JARVIS_PORT = "8001"` before starting. Use this entry point to apply host validation rather than overriding the binding through another launcher.

- Health: http://127.0.0.1:8000/health
- Offline API documentation: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

Documentation makes no CDN requests. Health reports backend liveness with `ai_connected: false`; it does not claim AI readiness. See [API reference](docs/API.md) for responses and error handling.

Run backend automated tests without starting a separate server:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
```

Phase 1 verification passed: automated API/configuration tests, dependency consistency, live startup, all three documented URLs, and loopback listener inspection. The current Starlette TestClient emits a non-failing deprecation warning about its HTTPX adapter; all tests pass. Direct dependency versions are pinned to the locally verified versions.

## Frontend scaffold

After explicit approval to install frontend dependencies, run from `frontend/`:

```powershell
npm install
npm run dev
```

Open the loopback URL printed by Vite, normally http://127.0.0.1:5173. The static scaffold page needs no backend. Commit the generated package lock after approved installation.

Type-check and build, then preview the output:

```powershell
npm run build
npm run preview
```

The build checks TypeScript before bundling. Frontend build and browser behavior remain unverified until dependencies are approved and installed.

See [architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).
