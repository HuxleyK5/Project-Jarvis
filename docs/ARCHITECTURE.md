# JARVIS Architecture

## Current scope

Phase 1 provides a local FastAPI backend and a minimal React/TypeScript/Vite frontend. The frontend renders a static status page without network requests or action controls.

Backend and frontend have independent dependencies and run lifecycles. Root `requirements.txt` owns Python runtime dependencies; `backend/tests/requirements.txt` adds test dependencies. `frontend/package.json` owns frontend dependencies. Neither imports the other's source. The current API contract is described in [API.md](API.md).

## Backend boundaries

- `core/`: application coordination and shared contracts.
- `voice/`: audio input and speech adapters.
- `memory/`: persistence interfaces and implementations.
- `automation/`: user-authorized action workflows.
- `tools/`: narrowly scoped capabilities.
- `integrations/`: model runtime and external service adapters.
- `tests/`: backend behavior verification.

Core contains Assistant health coordination and a Brain availability boundary that reports no connected model. Other capability packages reserve responsibilities, not working features. Future domain coordination should use explicit interfaces rather than depend directly on a UI, model vendor, or audio implementation.

## Frontend boundaries

- `components/`: reusable UI elements.
- `pages/`: complete page views.
- `services/`: future communication through documented backend contracts.
- `hooks/`: reusable React behavior.
- `styles/`: shared CSS.

`main.tsx` mounts React; `App.tsx` composes the scaffold page. No routing, state library, UI library, or HTTP client is needed. Vite uses its native TypeScript/JSX handling; no React plugin is required for this minimal page. Development and preview servers bind to loopback.

## Supporting directories

`data/` reserves local runtime storage, ignored except for its placeholder. `docs/` records environment facts and decisions. `scripts/` reserves future development helpers. Python initializers and `.gitkeep` files retain the directory structure in Git.

## Configuration and safety

Backend configuration stays separate from public browser configuration. `config.py` reads and validates JARVIS_HOST, JARVIS_PORT, and JARVIS_LOG_LEVEL from process environment variables using a frozen dataclass. Environment files are not automatically loaded. Never expose secrets in source or `VITE_` variables. Examples contain only nonsecret values. Ignore rules reduce accidental commits; review files before committing.

No microphone access, shell execution, credential handling, or computer control is implemented. Potentially destructive or security-sensitive features require explicit approval before implementation.

## Hardware decisions

The [hardware report](HARDWARE_REPORT.md) records Python 3.12.4, Node.js 20.16.0, approximately 16 GiB RAM, and 6 GiB VRAM. Python 3.12 and Vite 6 target those installed tools; official compatibility references are in the README. Backend startup and automated tests are verified locally; frontend build remains untested.

## Phase 1 HTTP composition

`backend/main.py` provides the FastAPI factory, lifespan, HTTP error translation, health endpoint, offline documentation, and validated loopback launcher. Each app creates an Assistant during startup. `core/assistant.py` reports health through `core/brain.py`, which has no inference implementation. There is no chat endpoint or simulated AI response.

Minimal Uvicorn runs one process without GPU libraries or optional server extras. HTTPX and standard-library unittest provide test coverage. No frontend integration or CORS access is enabled in this phase. Unexpected exceptions are logged locally and return generic JSON without internal details. The approved virtual environment is project-local; global Python and system settings are unchanged.

GPU and speech dependencies are deferred. Future model trials should start with small quantized models. D: offers more storage than C:, but no storage relocation, installation, or download is part of this scaffold.
