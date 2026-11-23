# JARVIS Local API v0.9.0

Start with `python -m backend.main` using the project virtual environment. Default base URL: `http://127.0.0.1:8000`. Ollama is the local text provider; voice input/output, memory and predefined computer tools are opt-in. JARVIS never pulls models. See [Ollama setup](OLLAMA_SETUP.md).

## Google productivity integrations

API v0.9 adds token-protected `/integrations/google` status, per-service settings/connect/disconnect, Calendar reads/event proposals, Gmail search/message/thread/local-summary and draft/send proposals, Classroom course/assignment reads, and exact-action execution/cancellation. Services default off. OAuth credentials are imported offline and encrypted with Windows-user DPAPI; access/refresh tokens never appear in status responses. The consent callback uses a temporary localhost listener with state/PKCE, not a public callback endpoint. Live API access still requires your own OAuth client, Google consent and any school/admin approval. See [GOOGLE_INTEGRATIONS.md](GOOGLE_INTEGRATIONS.md) for routes, scopes, setup and limits. Automatic workflows and `/chat` cannot issue Google writes.

## Computer tools

API v0.8 adds the token-protected `/automation` policy, natural-language/explicit plan, workflow start/cancel/schedule, session status and persistent metadata-history endpoints. Automatic low-risk actions require explicit session opt-in; significant actions require exact-plan approval. A blocked step prevents all execution. APScheduler scheduling is optional and unavailable until separately approved installation; immediate workflows need no new dependencies. See [AUTOMATION.md](AUTOMATION.md) for contracts and limitations. `/chat` still does not execute actions.

API v0.7 adds `/tools/session`, `/tools/policy`, `/tools/proposals`, `/tools/plan`, `/tools/operations/{id}` with execute/cancel actions, and `/tools/activity`. The session endpoint exposes the strict schema catalog to the localhost dashboard; other routes require the session header token. Permissions default off and require approval; every execution also requires approval of a validated, pending proposal. See [TOOLS.md](TOOLS.md) for request formats, errors, directory restrictions, metadata logging, cancellation and privacy limits. Ordinary `/chat` never executes tools.

| Method | Path | Result |
| --- | --- | --- |
| GET | /health | HTTP 200 backend liveness |
| GET | /docs | Self-contained HTML documentation without external resources |
| GET | /openapi.json | Generated OpenAPI schema |
| POST | /chat | Stream a local model reply using supplied session context |

Health response:

```json
{"status":"ok","service":"JARVIS","ai_connected":false,"provider":"ollama","model":"qwen3:4b","ai_status":"ollama_unavailable","ai_message":"Ollama is unavailable. Start the local service; see docs/OLLAMA_SETUP.md."}
```

Backend health stays HTTP 200 even if the model is missing. `ai_connected: true` means the selected model was found in a reachable Ollama service's installed model list. It does not mean the model is loaded or inference has succeeded. Discovery does not load a model. `ai_status` explains readiness (`ready`, `model_missing`, `remote_model`, `ollama_unavailable`, `ollama_timeout`, or `ollama_error`).

## Chat request and session context

```json
{"messages":[{"role":"user","content":"My name is Alex."},{"role":"assistant","content":"Hello, Alex."},{"role":"user","content":"What name did I give you?"}]}
```

This is an example API payload, not a claimed live model result. Messages alternate user/assistant, start with user, and end with a user question. System roles and extra fields are rejected; the backend injects its own JARVIS personality. Limits: 41 messages, 4000 characters per user message, 16000 per assistant-history message, and 40000 total content characters. Blank messages are invalid.

The browser owns session context. It sends recent completed pairs plus the current question. The backend retains the current question plus recent whole pairs, at most 10 preceding pairs, within an approximate character budget (twice context tokens, minimum 4000 characters). This is not exact token counting. Ollama enforces the configured token window; very long or multilingual context can still be truncated. Older turns eventually fall out of context. Temporary context is not stored between requests. Separately opted-in completed exchanges may be archived in SQLite; see the Phase 3 memory API below. Separate browser pages have separate transcripts; reload starts fresh. Failed, cancelled, or incomplete turns are not used as follow-up context by the frontend.

## Streaming response

Success is `application/x-ndjson` with one JSON event per line:

```json
{"type":"delta","content":"Hello"}
{"type":"delta","content":" there."}
{"type":"done","model":"qwen3:4b"}
```

Only `done` confirms a completed answer. A midstream failure produces an error event without a done event:

```json
{"type":"error","error":{"code":"incomplete_stream","message":"The response was interrupted before completion. Please retry."}}
```

The HTTP status cannot change after stream headers are sent. Clients must check error events and require done, including if a connection ends early. An output-token limit is reported as `output_limit` with incomplete text retained, rather than silently treating a cut-off answer as complete. The frontend renders model text as text, not executable HTML, and Stop aborts the request. Stream cleanup closes the provider iterator and releases the single-generation lock. There is no automatic retry that could duplicate turns.

Preflight failures use HTTP 503 for missing/unavailable models or HTTP 429 for an already busy model. A race for the generation slot can instead return a `model_busy` stream event. Total generation time defaults to 120 seconds; stalled individual reads time out after 30 seconds. No raw provider errors or prompts are returned in error messages or intentionally logged as transcripts. Models receive the supplied text, system prompt, and generation options; no tool definitions are supplied.

Error envelope:

```json
{"error":{"code":"http_404","message":"Not Found"}}
```

Unknown routes return 404. Unsupported methods return 405 with the Allow header. Invalid request data returns 422 with code `validation_error` and message `Invalid request data`. Unexpected failures return 500 with code `internal_error` and message `Internal server error`. Internal exception details are logged locally and not returned. Health takes no parameters; validation handling is exercised through a test-only route.

Implementation references: official FastAPI [error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/) and [testing](https://fastapi.tiangolo.com/tutorial/testing/) guidance, [Uvicorn settings](https://uvicorn.dev/settings/), and Ollama [chat](https://docs.ollama.com/api/chat), [model discovery](https://docs.ollama.com/api/tags), and [streaming](https://docs.ollama.com/api/streaming). The launcher explicitly binds to loopback and disables proxy-header interpretation.

## Phase 2 voice API

`GET /voice/status` reports `manual_available`, `wake_available`, `wake_phrase`, `sample_rate` (16000), `frame_samples` (1280), and a setup `message`. It does not load models or open microphones. Availability is dependency/file presence, not proof of inference compatibility.

`WS /voice/listen` requires a local dashboard Origin (HTTP localhost/127.0.0.1/::1 on 5173, 4173, or the configured backend port) and an initial JSON message `{"consent":true,"mode":"manual"}` or mode `wake`. No model work or audio is accepted before consent. Only one voice session may run at a time. Send binary 2560-byte frames containing mono, little-endian PCM16 at 16kHz. The server emits `state`, `transcript` (text), `no_speech` (message), and `error` (message) JSON events. Transcript text is then submitted by the dashboard to the existing chat endpoint.

Control messages: `{"type":"finish"}` ends the current utterance for transcription; `{"type":"stop"}` discards unfinished audio and closes; `{"type":"resume"}` resumes wake mode after a transcript/chat cycle. No audio is queued for another command while paused. Disconnects clear session buffers. Missing voice extras/assets return an error event rather than a transcript; the existing HTTP API remains available without them. Uvicorn needs the optional WebSocket transport for live browser voice, which has not been installed in this increment.

See [VOICE_SETUP.md](VOICE_SETUP.md) for privacy behavior, model licensing, asset setup, and test limits.

## Piper output API

`GET /speech/status` returns `available`, `voice`, and `message`, based on installed Piper metadata and local model/config existence. It performs no model download or synthesis.

`POST /speech/synthesize` accepts a JSON text field with 1-1000 nonblank characters; extra fields such as model paths are rejected. Successful replies are `audio/wav` with `Cache-Control: no-store`. Missing setup returns HTTP 503, a busy native job returns 429, synthesis failure returns 502, and a 60-second deadline returns 504, using the standard JSON error envelope. Audio is generated in memory. The browser owns playback, output routing, and interruption. See [SPEECH_OUTPUT.md](SPEECH_OUTPUT.md).

The voice socket also accepts `{"type":"ping"}` control messages so playback pauses do not require forwarding microphone audio. Wake acknowledgements are displayed separately from AI-generated replies and do not change the chat request contract.

## Phase 3 SQLite memory

Memory saving and retrieval are opt-in. `GET/PUT /memory/settings` manage enablement and separate future-history consent. `GET/POST /memory/entries` list/search or approve preferences/projects/facts; `PUT/DELETE /memory/entries/{id}` edit/delete. `GET /memory/conversations?q=...` searches archived exchanges; `DELETE /memory/conversations/{turn_id}` deletes one. Saving/editing requires `approved:true`; deletion requires `confirm=true`. Sensitive patterns are rejected, and duplicate memories return 409.

Optional `/chat` fields `save_history:true`, `conversation_id`, and `turn_id` (UUIDs) request saving the current completed pair when persisted history consent is also enabled. A memory status event (`saved`, `duplicate`, `disabled`, `skipped_sensitive`, or `error`) precedes done. Failed/non-opted-in turns are not archived. Approved entries may be retrieved for AI reference independently of temporary context. See [MEMORY.md](MEMORY.md) for payloads, defaults, privacy limitations, and restart verification.

## Conversation continuity and personalization

Optional chat fields: `context_summary` is temporary, untrusted extractive text (max 5000 characters); `assistant_preferences` contains only tone (`professional`, `friendly`, `formal`) and detail (`balanced`, `concise`, `detailed`). Request style overrides the approved saved style for that session without writing it. Neither summaries nor retrieved data are included in archive persistence.

`GET /memory/personality` returns authorized saved style or defaults. `PUT /memory/personality` requires tone/detail, `approved:true`, and enabled memory. `PUT /memory/settings` now accepts separate `recall_history` consent, default false. Archive recall requires that permission, enabled memory, and a prior-conversation reference. Saved preferences now require relevance, rather than being inserted into every response. See [CONVERSATION.md](CONVERSATION.md) for bounded context behavior and schema compatibility.
