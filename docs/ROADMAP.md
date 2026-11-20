# JARVIS Roadmap

Only individual user prompts authorize implementation. This roadmap does not authorize future work.

| Milestone | Scope | Status |
| --- | --- | --- |
| Phase 0: inspection | Read-only hardware/tool inventory and hardware report | Complete; actual audio and inference performance untested |
| Initial structure | Independent Python backend, React/TypeScript/Vite scaffold, documentation and configuration examples | Complete; frontend dependencies installed with approval |
| Phase 1: backend foundation | Local FastAPI, health, configuration, errors, documentation, and tests | Complete; automated tests and live loopback startup verified |
| Desktop dashboard | Responsive HUD, live backend connection, session conversation, activity, and browser tests | Complete; production build, 6 browser tests, real API connection, and local production preview verified |
| Local AI brain | Configurable Ollama provider, streamed chat, bounded follow-up context, personality, errors, tests, and setup guide | Implemented; actual inference blocked by unavailable Ollama and unfulfilled current OS/driver prerequisites |
| Phase 2: voice input | Manual capture, pretrained Hey JARVIS integration, local STT, consent/start/stop controls, tests, and setup documentation | Implemented; real inference awaits separately approved dependencies/models |
| Piper voice output | Local synthesis, playback/device controls, interruption, wake acknowledgement, feedback suppression, and tests | Implemented; real inference/hardware conversation awaits approved prerequisites |
| Phase 3: SQLite memory | Approved entries, opt-in archives, retrieval, search/edit/delete, privacy controls, and restart tests | Implemented; SQLite persistence verified across actual backend process restart |
| Conversation intelligence | Follow-up context, relevant memory, approved archive recall, extractive summaries, configurable style, and tests | Implemented; live model quality awaits available Ollama |
| Phase 4: computer tools | Schema registry, local permissions, per-action approval, system/file tools, approved Windows app/site opening, cancellation and audit activity | Implemented; native launch handoffs and AI selection tested with injected adapters/provider; live Ollama quality unverified |
| Future phases | Scope to be provided by the user | Not specified or implemented |

For each increment: inspect the existing project, preserve working behavior, implement only the requested scope, test important behavior, explain affected files and run/test steps, then stop.

Obtain approval before dependency installation, model downloads, or system setting changes. Ask before implementing destructive or security-sensitive operations. Autonomous automation, destructive tools, and additional providers remain deferred.
