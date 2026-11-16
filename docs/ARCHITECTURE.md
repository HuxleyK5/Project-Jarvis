# JARVIS Architecture

## Current scope

The local FastAPI backend has an independent React/TypeScript/Vite HUD dashboard and a local Ollama conversation brain. The dashboard streams actual provider responses and maintains conversation/activity in browser-session memory. Voice recognition, persistent memory, and computer control remain unimplemented. Actual model inference is unverified on this computer because Ollama is unavailable; see [setup and compatibility](OLLAMA_SETUP.md).

Backend and frontend have independent dependencies and run lifecycles. Root `requirements.txt` owns Python runtime dependencies; `backend/tests/requirements.txt` adds test dependencies. `frontend/package.json` owns frontend dependencies. Neither imports the other's source. The current API contract is described in [API.md](API.md).

## Backend boundaries

- `core/`: application coordination and shared contracts.
- `voice/`: audio input and speech adapters.
- `memory/`: persistence interfaces and implementations.
- `automation/`: user-authorized action workflows.
- `tools/`: narrowly scoped capabilities.
- `integrations/`: model runtime and external service adapters.
- `tests/`: backend behavior verification.

Core contains Assistant health coordination, Brain conversation/context policy, the server-owned personality, and a ModelProvider protocol. The provider factory in integrations selects the Ollama adapter. Brain depends on the protocol rather than an Ollama transport. OllamaProvider owns HTTPX communication, model discovery, stream parsing, and provider-specific errors. Other capability packages reserve responsibilities, not working features.

## Frontend boundaries

- `components/`: reusable UI elements.
- `pages/`: complete page views.
- `services/`: validated health requests and NDJSON chat parsing through the backend contract.
- `hooks/`: reusable React behavior.
- `styles/`: shared CSS.

`main.tsx` mounts React; `App.tsx` composes the dashboard page. `components/AssistantCore.tsx` provides decorative HUD animation; `components/Icon.tsx` supplies local SVG icons. `hooks/useBackend.ts` manages health polling, timeout, cancellation, and retry. `services/api.ts` validates health responses at runtime. No routing, state library, UI library, or HTTP client dependency is needed. Vite handles TypeScript/JSX. Development and preview servers bind to loopback.

Vite proxies same-origin `/api/*` to `http://127.0.0.1:8000/*`, including health and chat, in both development and preview. The browser makes no cross-origin API requests, and backend CORS policy is unchanged. The proxy target is configured in `frontend/vite.config.ts`. This proxy must be provided separately if static output is ever hosted outside Vite; remote hosting is outside scope.

Health polls every 10 seconds, times out after 4 seconds, and cancels pending work on cleanup. Loss of connection clears stale model status. `useChat.ts` serializes user sends, tracks streaming/complete/failed/stopped states, and aborts on Stop, page cleanup, or its 180-second deadline. `services/chat.ts` incrementally decodes UTF-8 NDJSON, requires a done event, and surfaces partial failures. Messages are React text nodes, not interpreted HTML. Audio and resource telemetry are not simulated. Date/time uses the browser clock. Hardware data is explicitly the Phase 0 snapshot. Activity history is bounded to 50 events, and all conversation/activity state clears on reload.

The frontend keeps up to 10 completed pairs and 30000 context characters for request construction, plus the latest question; only completed exchanges enter that context. The backend further bounds recent whole pairs for the configured model window. Full visible session history can outlast the shorter model-context window; follow-ups about older omitted turns may require restating information. Request validation rejects client system roles, invalid ordering, and oversized content. There is no server-side session store or durable memory.

## Supporting directories

`data/` reserves local runtime storage, ignored except for its placeholder. `docs/` records environment facts and decisions. `scripts/` reserves future development helpers. Python initializers and `.gitkeep` files retain the directory structure in Git.

## Configuration and safety

Backend configuration stays separate from public browser configuration. `config.py` reads and validates JARVIS_HOST, JARVIS_PORT, and JARVIS_LOG_LEVEL from process environment variables using a frozen dataclass. Environment files are not automatically loaded. Never expose secrets in source or `VITE_` variables. Examples contain only nonsecret values. Ignore rules reduce accidental commits; review files before committing.

No microphone access, shell execution, credential handling, or computer control is implemented. Potentially destructive or security-sensitive features require explicit approval before implementation.

## Hardware decisions

The [hardware report](HARDWARE_REPORT.md) records Python 3.12.4, Node.js 20.16.0, approximately 16 GiB RAM, and 6 GiB VRAM. Python 3.12 and Vite 6 target those installed tools; official compatibility references are in the README. Backend tests, frontend builds, and Chromium browser integration are verified locally. Lightweight CSS/SVG animation avoids a 3D rendering dependency and honors reduced-motion preferences.

## Phase 1 HTTP composition

`backend/main.py` provides the FastAPI factory, lifespan, HTTP error translation, health endpoint, streamed `/chat`, offline documentation, and loopback launcher. The lifespan constructs the configured provider/Brain/Assistant and closes the provider client on shutdown. Injected providers support deterministic tests without production fallback answers. One generation lock limits local GPU overlap; total generation deadlines and provider read timeouts bound stalls. Disconnect cleanup closes the stream iterator and releases the lock. Pre-stream failures are JSON HTTP errors; later failures are NDJSON error events.

Minimal Uvicorn runs one process without GPU libraries or optional server extras. HTTPX and standard-library unittest cover the backend; Playwright covers browser behavior and the real health connection. No CORS access is enabled. Unexpected exceptions are logged locally and return generic JSON without internal details. The approved virtual environment is project-local; global Python and system settings are unchanged.

HTTPX is now a runtime dependency and was already installed in the approved virtual environment. No Ollama SDK or GPU framework was added. Settings select `ollama` and default to the hardware report's `qwen3:4b`, 4096 context tokens, and 512 output tokens. The adapter sends no tools and disables separate thinking output. Its HTTP client ignores proxy environment variables, refuses redirects, and uses a validated loopback HTTP origin. Known cloud tags and entries advertising remote metadata are rejected. JARVIS calls only model listing and chat endpoints, never pull/install endpoints. Switching an installed model requires an environment setting and restart; adding a provider requires a protocol adapter, factory registration, and validation update.

Ollama itself controls model loading and GPU/CPU execution. Current machine Windows/driver versions are below current Ollama prerequisites; no system changes, installation, model download, or storage relocation was performed. Natural-language quality and GPU behavior remain unverified. The personality is guidance to the model, not a guarantee against hallucinations.
