# JARVIS

Personal AI assistant project built incrementally. Current scope: local Ollama conversation brain, streaming FastAPI chat, and responsive React dashboard. Phase 2 adds opt-in local voice input; optional Piper voice output is now implemented. Computer control, automation, and persistent memory are not implemented.

This repository is the JARVIS root; no nested JARVIS directory is needed.

## Directory guide

| Directory | Purpose |
| --- | --- |
| backend/ | Independent Python backend package |
| backend/core/ | Assistant coordination, personality, context policy, and provider contract |
| backend/voice/ | Optional wake detection, speech recognition, consent-gated audio sessions, and diagnostics |
| backend/memory/ | Future persistence interfaces and implementations |
| backend/automation/ | Future user-authorized action workflows |
| backend/tools/ | Future narrowly scoped assistant capabilities |
| backend/integrations/ | Local Ollama adapter and provider factory |
| backend/tests/ | Backend tests |
| frontend/ | Independent React, TypeScript, and Vite dashboard |
| frontend/src/components/ | Reusable UI elements |
| frontend/src/pages/ | Page-level views |
| frontend/src/services/ | Typed health client and streamed chat transport |
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

For runtime-only dependencies use `-r requirements.txt`. The already-installed HTTPX now also handles Ollama requests; no new package installation was needed for the AI brain. No environment activation or execution-policy change is needed.

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m backend.main
```

The server binds to `127.0.0.1:8000`. Stop it with Ctrl+C. To choose another local port, set `$env:JARVIS_PORT = "8001"` before starting. Use this entry point to apply host validation rather than overriding the binding through another launcher.

- Health: http://127.0.0.1:8000/health
- Offline API documentation: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

Documentation makes no CDN requests. Health always distinguishes backend liveness from model availability: `ai_connected`, `provider`, `model`, `ai_status`, and `ai_message` reflect local Ollama discovery. Availability means the model is installed and the service is reachable, not that inference has been verified. See [API reference](docs/API.md).

## Local AI brain

The default is **qwen3:4b**, following the hardware report's preferred small quantized model range, with a 4096-token context and 512-token output limit. Set `$env:JARVIS_MODEL = "another-installed-model"` before backend startup to change models. Model/provider settings and timeouts are documented in `.env.example` and [Ollama setup](docs/OLLAMA_SETUP.md). Restart after changing configuration. All Ollama requests use a validated loopback HTTP origin; JARVIS never downloads models automatically.

**Current setup limit:** Ollama was not reachable on November 16, 2026. The machine's Windows build and NVIDIA driver are below current Ollama prerequisites. Actual AI communication remains untested. Follow the compatibility review and approval-dependent setup steps in [OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) before installing anything or downloading a model.

Run backend automated tests without starting a separate server:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
```

Phase 1 verification passed: automated API/configuration tests, dependency consistency, live startup, all three documented URLs, and loopback listener inspection. The current Starlette TestClient emits a non-failing deprecation warning about its HTTPX adapter; all tests pass. Direct dependency versions are pinned to the locally verified versions.

## Desktop dashboard

Frontend dependencies and Playwright were installed with approval. Start the backend in one terminal using the instructions above. In another terminal, from `frontend/`:

```powershell
npm run dev
```

Open http://127.0.0.1:5173 in your browser on this computer. Keep both terminals running. The frontend and backend bind only to loopback; the frontend calls `/api/health` through Vite's local proxy to `127.0.0.1:8000`. If the backend port changes, update the proxy target in `frontend/vite.config.ts` as well. A port already in use produces an explicit error rather than silently choosing another port.

The HUD includes an animated core, session conversation, activity history, system status, date/time in your browser's timezone, and a command input. Health checks run immediately and every 10 seconds, with a 4-second timeout and a manual refresh control. Connection failures and reconnections are shown honestly.

Typed messages now call `POST /api/chat`, proxied to backend `/chat`, and model text appears as it streams. Stop cancels the request. Recent successfully completed question/answer pairs are sent with follow-up questions; failed, cancelled, and partial turns remain visible but are excluded from context. Transcripts live only in browser memory and clear on reload. Backend restart alone does not erase the open page's context; reloading it does. Activity history keeps the latest 50 session events. Provider errors are shown explicitly without generated fallback replies.

JARVIS's system personality is professional, conversational, helpful, and instructed to admit uncertainty and capability limits. Model output can still be wrong. No tools or computer control are exposed. Voice input requires session consent; the waveform shows microphone level only while active. Workstation specifications remain the Phase 0 snapshot. Reduced-motion preferences disable decorative animation.

Type-check and build, then preview the output:

```powershell
npm run build
npm run preview
```

The build checks TypeScript before bundling. Preview runs at http://127.0.0.1:4173 and uses the same local API proxy. This is a local browser dashboard, not a packaged native executable; no desktop wrapper was added.

Run browser tests from `frontend/`:

```powershell
npm test
```

Playwright starts local servers when necessary, reuses existing servers, and closes servers it started. Restart any older running backend before testing new code. Tests cover the real health connection, missing-provider behavior, streamed chat/context, stop/error states, reconnection, and responsive layouts. Chat replies in browser tests are test-only intercepted streams, not live model inference. Screenshots are written to ignored `frontend/test-results/`.

For a fresh checkout, obtain dependency/download approval before `npm ci` and `npx playwright install chromium`. The lockfile records frontend dependencies. Browser binaries use Playwright's normal local user cache. No external fonts, assets, or paid services are required at runtime.

See [architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).

## Phase 2 voice input

Manual microphone capture and continuous **Hey JARVIS** wake listening are implemented as optional features. Both consent and continuous listening default to off. The browser checks local setup before asking for microphone permission. Stop, consent withdrawal, changing listening mode, and page cleanup release microphone tracks. Recognized speech uses the existing chat flow and appears as **YOU · VOICE**; optional Piper playback is documented below.

**Per your decision, no voice dependencies were installed and no models were downloaded.** Voice therefore reports missing setup on this computer. Typed chat remains available. Actual wake accuracy, speech-recognition accuracy, and physical microphone compatibility are unverified. See [VOICE_SETUP.md](docs/VOICE_SETUP.md) for local asset paths, pretrained-model limitations/licensing, privacy behavior, and future approval-dependent setup.

Audio stays in bounded memory and is not saved to files. A capture is capped at 12 seconds; Stop discards it rather than transcribing it. Continuous mode pauses audio forwarding during transcription/chat, while the browser microphone remains active until Stop. The included pretrained English detector is not speaker authentication.

Run wake and speech tests separately from the project root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p "test_voice_wake.py" -v
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p "test_voice_speech.py" -v
```

The normal backend and frontend startup commands above are unchanged. Voice readiness is available at `http://127.0.0.1:8000/voice/status`. Browser tests use synthetic audio and intercepted model events; they do not open a physical microphone or validate real model inference.

## Local Piper voice output

Voice output is off by default. The **VOICE OUTPUT** panel provides enable/disable, output-device selection where supported, volume, playback speed, pause/resume, Stop, and Replay. Completed AI responses are displayed first and spoken locally in sequential chunks. New input interrupts old playback. The waveform measures the active playback graph. Wake mode adds the labeled acknowledgement "Yes, how can I help?", waits for its playback, then captures the command; microphone forwarding is paused during speech.

**Piper and its voice were not installed/downloaded, per your decision.** Full application flow is tested with synthetic audio and mocked models; live Piper inference, physical output routing, and a real full voice conversation remain unverified. Existing voice-input model restrictions still apply. Missing speech setup produces clear errors without breaking text chat.

See [SPEECH_OUTPUT.md](docs/SPEECH_OUTPUT.md) for optional requirements, voice asset paths, settings, licensing references, controls, and real acceptance steps. Restart the backend to load `/speech/status` and `/speech/synthesize`. Normal startup and test commands above remain unchanged. No generated audio files are saved.
