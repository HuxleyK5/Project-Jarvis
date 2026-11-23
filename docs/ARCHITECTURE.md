# JARVIS Architecture

## Current scope

The local FastAPI backend has an independent React/TypeScript/Vite HUD dashboard and a local Ollama conversation brain. The dashboard streams actual provider responses and maintains conversation/activity in browser-session memory. Optional local voice input, Piper output, opt-in SQLite memory, and predefined approval-controlled computer tools are implemented. Actual model inference is unverified on this computer because Ollama is unavailable; see [setup and compatibility](OLLAMA_SETUP.md).

Backend and frontend have independent dependencies and run lifecycles. Root `requirements.txt` owns Python runtime dependencies; `backend/tests/requirements.txt` adds test dependencies. `frontend/package.json` owns frontend dependencies. Neither imports the other's source. The current API contract is described in [API.md](API.md).

## Backend boundaries

- `core/`: application coordination and shared contracts.
- `voice/`: audio input and speech adapters.
- `memory/`: persistence interfaces and implementations.
- `automation/`: user-authorized action workflows.
- `tools/`: narrowly scoped capabilities.
- `integrations/`: model runtime and external service adapters.
- `tests/`: backend behavior verification.

Core contains Assistant health coordination, Brain conversation/context policy, the server-owned personality, and a ModelProvider protocol. The provider factory in integrations selects the Ollama adapter. Brain depends on the protocol rather than an Ollama transport. OllamaProvider owns HTTPX communication, model discovery, stream parsing, and provider-specific errors.

`tools/registry.py` owns the fixed capability catalog, strict schemas, session allowlists, path boundaries, pending proposals, cooperative workers, results and metadata audit. `tools/api.py` owns same-origin/loopback request protection, session tokens, explicit permission/action approval, polling and cancellation. `Brain.select_tool` can propose one tool through the existing provider; registry validation and dashboard approval remain independent of model output. `ToolPanel.tsx` displays permissions, manual/AI proposals, exact action previews and escaped results, and forwards metadata transitions into the existing activity feed. File data is never injected into model context or saved as memory by this subsystem. See [TOOLS.md](TOOLS.md).

`automation/models.py` defines strict bounded plans; `policy.py` assigns automatic/confirmation/blocked categories independently of the model. `engine.py` owns immutable session plans, permission snapshots, ordered execution over the existing registry, cancellation, deadlines and partial reports. `verification.py` checks observable tool contracts. `history.py` appends metadata only, separately from conversation memory. `scheduler.py` isolates optional APScheduler 3.x one-time starts; no schedule survives restart or restores old approval. `automation/api.py` reuses the local tool token/origin protection. Brain's workflow planner shares the existing provider/generation lock and returns JSON plans, never executable code. `AutomationPanel.tsx`, `useAutomation.ts` and `services/automation.ts` provide preview, exact-plan approval, status/history and cancellation without changing the ordinary chat contract. See [AUTOMATION.md](AUTOMATION.md).

`integrations/google/manager.py` is the modular Google service registry and write-proposal coordinator. `calendar.py`, `gmail.py`, and `classroom.py` own separate official REST contracts; `transport.py` enforces fixed origins, bounded responses, safe errors and no write retries. `oauth.py` owns per-service scopes, refresh locks, PKCE/state and ephemeral loopback consent; `secure_store.py` isolates current-Windows-user DPAPI and `setup.py` imports a user-provided desktop client offline. `privacy.py` redacts Google request logging. `api.py` reuses existing local session protection, rather than exposing secrets or broadly opening CORS. Google adapters are not registered as automatic workflow tools. Brain's explicit email-summary method consumes bounded untrusted excerpts through the local model with no tool/memory context. `GooglePanel.tsx` handles capabilities/auth status and exact external-action approval; `GoogleData.tsx` renders each service's data with escaped text. See [GOOGLE_INTEGRATIONS.md](GOOGLE_INTEGRATIONS.md).

## Frontend boundaries

- `components/`: reusable UI elements.
- `pages/`: complete page views.
- `services/`: validated health requests and NDJSON chat parsing through the backend contract.
- `hooks/`: reusable React behavior.
- `styles/`: shared CSS.

`main.tsx` mounts React; `App.tsx` composes the dashboard page. `components/AssistantCore.tsx` provides decorative HUD animation; `components/Icon.tsx` supplies local SVG icons. `hooks/useBackend.ts` manages health polling, timeout, cancellation, and retry. `services/api.ts` validates health responses at runtime. No routing, state library, UI library, or HTTP client dependency is needed. Vite handles TypeScript/JSX. Development and preview servers bind to loopback.

Vite proxies same-origin `/api/*` to `http://127.0.0.1:8000/*`, including health and chat, in both development and preview. The browser makes no cross-origin API requests, and backend CORS policy is unchanged. The proxy target is configured in `frontend/vite.config.ts`. This proxy must be provided separately if static output is ever hosted outside Vite; remote hosting is outside scope.

Health polls every 10 seconds, times out after 4 seconds, and cancels pending work on cleanup. Loss of connection clears stale model status. `useChat.ts` serializes user sends, tracks streaming/complete/failed/stopped states, and aborts on Stop, page cleanup, or its 180-second deadline. `services/chat.ts` incrementally decodes UTF-8 NDJSON, requires a done event, and surfaces partial failures. Messages are React text nodes, not interpreted HTML. Audio and resource telemetry are not simulated. Date/time uses the browser clock. Hardware data is explicitly the Phase 0 snapshot. Activity history is bounded to 50 events, and all conversation/activity state clears on reload.

The frontend keeps up to 10 completed pairs and 30000 context characters for request construction, plus the latest question; only completed exchanges enter that context. The backend further bounds recent whole pairs for the configured model window. Full visible session history can outlast the shorter model-context window; follow-ups about older omitted turns may require restating information. Request validation rejects client system roles, invalid ordering, and oversized content. There is no server-side temporary-session store. Durable SQLite memory is a separate opt-in subsystem described below.

## Supporting directories

`data/` reserves local runtime storage, ignored except for its placeholder. `docs/` records environment facts and decisions. `scripts/` reserves future development helpers. Python initializers and `.gitkeep` files retain the directory structure in Git.

## Configuration and safety

Backend configuration stays separate from public browser configuration. `config.py` reads and validates JARVIS_HOST, JARVIS_PORT, and JARVIS_LOG_LEVEL from process environment variables using a frozen dataclass. Environment files are not automatically loaded. Never expose secrets in source or `VITE_` variables. Examples contain only nonsecret values. Ignore rules reduce accidental commits; review files before committing.

Microphone access is session-consent-gated and browser-controlled. Single computer tools use a fixed catalog and explicit per-action approval. Approved bounded workflows may sequence these tools under a separate automatic/confirmation/blocked policy. No arbitrary shell execution, document modification, credential tool, or unrestricted autonomous agent is provided.

## Hardware decisions

The [hardware report](HARDWARE_REPORT.md) records Python 3.12.4, Node.js 20.16.0, approximately 16 GiB RAM, and 6 GiB VRAM. Python 3.12 and Vite 6 target those installed tools; official compatibility references are in the README. Backend tests, frontend builds, and Chromium browser integration are verified locally. Lightweight CSS/SVG animation avoids a 3D rendering dependency and honors reduced-motion preferences.

## Phase 1 HTTP composition

`backend/main.py` provides the FastAPI factory, lifespan, HTTP error translation, health endpoint, streamed `/chat`, offline documentation, and loopback launcher. The lifespan constructs the configured provider/Brain/Assistant and closes the provider client on shutdown. Injected providers support deterministic tests without production fallback answers. One generation lock limits local GPU overlap; total generation deadlines and provider read timeouts bound stalls. Disconnect cleanup closes the stream iterator and releases the lock. Pre-stream failures are JSON HTTP errors; later failures are NDJSON error events.

Minimal Uvicorn runs one process without GPU libraries or optional server extras. HTTPX and standard-library unittest cover the backend; Playwright covers browser behavior and the real health connection. No CORS access is enabled. Unexpected exceptions are logged locally and return generic JSON without internal details. The approved virtual environment is project-local; global Python and system settings are unchanged.

HTTPX is now a runtime dependency and was already installed in the approved virtual environment. No Ollama SDK or GPU framework was added. Settings select `ollama` and default to the hardware report's `qwen3:4b`, 4096 context tokens, and 512 output tokens. The adapter sends no tools and disables separate thinking output. Its HTTP client ignores proxy environment variables, refuses redirects, and uses a validated loopback HTTP origin. Known cloud tags and entries advertising remote metadata are rejected. JARVIS calls only model listing and chat endpoints, never pull/install endpoints. Switching an installed model requires an environment setting and restart; adding a provider requires a protocol adapter, factory registration, and validation update.

Ollama itself controls model loading and GPU/CPU execution. Current machine Windows/driver versions are below current Ollama prerequisites; no system changes, installation, model download, or storage relocation was performed. Natural-language quality and GPU behavior remain unverified. The personality is guidance to the model, not a guarantee against hallucinations.

## Phase 2 voice boundaries

`voice/config.py` defines independent voice settings. `voice/engines.py` lazily loads explicit local OpenWakeWord ONNX assets and a CPU/INT8 Faster-Whisper directory, never downloading models. `voice/session.py` owns wake thresholding, silence/click suppression, a 12-second utterance cap, and in-memory PCM cleanup. `voice/api.py` provides asset readiness and a local-Origin, explicit-consent WebSocket with one active session and a dedicated inference worker. Stop discards audio; finish requests transcription; continuous mode requires resume after each transcript. An already running native inference call may finish after cancellation, but stopped clients ignore its result. No audio files or transcript logs are written by the voice pipeline.

`frontend/public/audio-capture.js` mixes/resamples browser audio into 1280-sample little-endian PCM16 frames. `useVoice.ts` owns microphone permission, device errors, the muted audio graph, WebSocket backpressure, and track cleanup. `VoiceControls.tsx` exposes unchecked session consent and continuous-listening controls. Speech text is labeled in conversation and passed through `useChat`; if chat is busy/offline it is placed in the draft input. Typed submission stops active voice capture to avoid overlapping input.

The Vite proxy enables WebSocket upgrades for `/api/voice/listen`. Voice dependencies remain separate in `backend/voice/requirements.txt`; they were not installed, and assets were not downloaded, per the user's decision. Wake and speech are tested independently using injected components. Browser tests use synthetic audio, not physical microphones. Real model inference, native runtime compatibility, and detection accuracy remain unverified. See [VOICE_SETUP.md](VOICE_SETUP.md).

## Piper voice output

`backend/voice/tts.py` defines validated environment settings, lazy CPU-only Piper loading, a non-overlapping native synthesis worker, and `/speech/status` plus `/speech/synthesize`. WAV data is generated in memory and sent without persistent caching. Local model/config files are required; there is no implicit downloader. Request cancellation cannot preempt running native inference, so the service keeps tracking the native Future and refuses another job until it finishes.

`useSpeech.ts` owns one Web Audio playback graph, analyser-based level metering, output sink selection, volume/speed, pause/resume, Stop/replay, and stale-request suppression. It processes response chunks sequentially rather than creating overlapping sources. `SpeechControls.tsx` exposes session-only opt-in controls. `useChat` returns only completed answers for synthesis; wake acknowledgements are explicitly labeled display messages excluded from AI context. `useVoice` awaits wake acknowledgement/reply playback before capture resumes and blocks microphone forwarding while speech output is active. Audio-free heartbeat controls keep the consented socket alive during playback.

Optional Piper requirements are isolated in `backend/voice/tts-requirements.txt`. They and the voice model were not installed/downloaded. See [SPEECH_OUTPUT.md](SPEECH_OUTPUT.md) for output-selection browser limits and real-inference/hardware verification limits. No spoken-response provider fallback or unrelated automation was added.

## Phase 3 memory boundary

`backend/memory/manager.py` owns SQLite settings, approved entries, archived completed pairs, parameterized search, deduplication, and deletion. `privacy.py` applies conservative sensitive-content rejection before persistence. `api.py` exposes explicit approval and confirmation controls. The file is not created at startup or by reads when missing. Connections are short-lived; write transactions recheck consent while serialized. No new dependency or external embedding service is required.

Brain receives an optional manager and adds only bounded relevant approved entries as reference data. The AI cannot create/edit/delete memories through tools. Chat archiving requires both persisted consent and per-request opt-in; only the newly completed pair is written, never the request's full temporary history. A memory status event explains the result before done; failures do not discard a successful AI reply. Conversation archives remain separate and are not automatically injected as facts.

`useMemory.ts`, `services/memory.ts`, and `MemoryPanel.tsx` provide session-safe settings loading, approval reset on edits, search, and confirmed deletion. Memory/history defaults are off. SQLite data is local, unencrypted, ignored by Git, and not remotely synced. Sensitive detection is heuristic, not a guarantee for arbitrary unlabeled secrets. See [MEMORY.md](MEMORY.md) for limits and restart tests.

## Conversation continuity and style

`core/context.py` detects bounded follow-up/archive-reference signals and produces retrieval terms. `core/personality.py` defines validated tone/detail choices. Brain combines recent whole turns, untrusted extractive summary quotes, relevant approved memories, and separately authorized archive excerpts within a shared approximate prompt budget. Facts, user-reported claims, assumptions, and unknowns are distinguished through explicit model policy. No automatic memory writes or tools are introduced.

`services/context.ts` condenses evicted completed browser turns into bounded source-labelled quotes; `useChat` sends that temporary summary independently of archive fields. `useAssistantPreferences` and its component provide session-only style and separately approved persistence. SQLite options add schema v2 without changing existing memory/history rows. Archive retrieval requires both explicit reference intent and the separate recall permission. See [CONVERSATION.md](CONVERSATION.md) for full limits and tests; previous Phase 3 descriptions of unconditional preference priority/no archive injection are superseded by these opt-in relevance rules.
