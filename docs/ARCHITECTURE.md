# JARVIS Architecture

## Current scope

The local FastAPI backend now has an independent React/TypeScript/Vite HUD dashboard. The dashboard reads real backend health and maintains conversation and activity history in session memory. AI inference, voice recognition, and computer control remain unimplemented.

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
- `services/`: typed, validated health requests through the existing backend contract.
- `hooks/`: reusable React behavior.
- `styles/`: shared CSS.

`main.tsx` mounts React; `App.tsx` composes the dashboard page. `components/AssistantCore.tsx` provides decorative HUD animation; `components/Icon.tsx` supplies local SVG icons. `hooks/useBackend.ts` manages health polling, timeout, cancellation, and retry. `services/api.ts` validates health responses at runtime. No routing, state library, UI library, or HTTP client dependency is needed. Vite handles TypeScript/JSX. Development and preview servers bind to loopback.

Vite proxies same-origin `/api/health` to `http://127.0.0.1:8000/health` in both development and preview. The browser makes no cross-origin API requests, and backend CORS policy is unchanged. The proxy target is configured in `frontend/vite.config.ts`. This proxy must be provided separately if static output is ever hosted outside Vite; remote hosting is outside scope.

Health polls every 10 seconds, times out after 4 seconds, and cancels pending work on cleanup. Loss of connection clears stale model status. Session messages are never sent to a nonexistent chat endpoint; UI labels explain this. Messages are React text nodes, not interpreted HTML. Audio and resource telemetry are not simulated. Date/time uses the browser clock. Hardware data is explicitly the Phase 0 snapshot. Activity history is bounded to 50 events, and all conversation/activity state clears on reload.

## Supporting directories

`data/` reserves local runtime storage, ignored except for its placeholder. `docs/` records environment facts and decisions. `scripts/` reserves future development helpers. Python initializers and `.gitkeep` files retain the directory structure in Git.

## Configuration and safety

Backend configuration stays separate from public browser configuration. `config.py` reads and validates JARVIS_HOST, JARVIS_PORT, and JARVIS_LOG_LEVEL from process environment variables using a frozen dataclass. Environment files are not automatically loaded. Never expose secrets in source or `VITE_` variables. Examples contain only nonsecret values. Ignore rules reduce accidental commits; review files before committing.

No microphone access, shell execution, credential handling, or computer control is implemented. Potentially destructive or security-sensitive features require explicit approval before implementation.

## Hardware decisions

The [hardware report](HARDWARE_REPORT.md) records Python 3.12.4, Node.js 20.16.0, approximately 16 GiB RAM, and 6 GiB VRAM. Python 3.12 and Vite 6 target those installed tools; official compatibility references are in the README. Backend tests, frontend builds, and Chromium browser integration are verified locally. Lightweight CSS/SVG animation avoids a 3D rendering dependency and honors reduced-motion preferences.

## Phase 1 HTTP composition

`backend/main.py` provides the FastAPI factory, lifespan, HTTP error translation, health endpoint, offline documentation, and validated loopback launcher. Each app creates an Assistant during startup. `core/assistant.py` reports health through `core/brain.py`, which has no inference implementation. There is no chat endpoint or simulated AI response.

Minimal Uvicorn runs one process without GPU libraries or optional server extras. HTTPX and standard-library unittest cover the backend; Playwright covers browser behavior and the real health connection. No CORS access is enabled. Unexpected exceptions are logged locally and return generic JSON without internal details. The approved virtual environment is project-local; global Python and system settings are unchanged.

GPU and speech dependencies are deferred. Future model trials should start with small quantized models. D: offers more storage than C:, but no storage relocation, installation, or download is part of this scaffold.
