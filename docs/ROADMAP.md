# JARVIS Roadmap

Only individual user prompts authorize implementation. This roadmap does not authorize future work.

| Milestone | Scope | Status |
| --- | --- | --- |
| Phase 0: inspection | Read-only hardware/tool inventory and hardware report | Complete; actual audio and inference performance untested |
| Initial structure | Independent Python backend, React/TypeScript/Vite scaffold, documentation and configuration examples | Created; frontend build awaits approved dependency installation |
| Phase 1: backend foundation | Local FastAPI, health, configuration, errors, documentation, and tests | Complete; automated tests and live loopback startup verified |
| Future phases | Scope to be provided by the user | Not specified or implemented |

For each increment: inspect the existing project, preserve working behavior, implement only the requested scope, test important behavior, explain affected files and run/test steps, then stop.

Obtain approval before dependency installation, model downloads, or system setting changes. Ask before implementing destructive or security-sensitive operations. AI inference, voice recognition, automation, memory behavior, and integrations remain deferred.
