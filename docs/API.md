# JARVIS Local API v0.2.0

Start with `python -m backend.main` using the project virtual environment. Default base URL: `http://127.0.0.1:8000`. Ollama is the local text provider; voice and computer control are not implemented. JARVIS never pulls models. See [Ollama setup](OLLAMA_SETUP.md).

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

The browser owns session context. It sends recent completed pairs plus the current question. The backend retains the current question plus recent whole pairs, at most 10 preceding pairs, within an approximate character budget (twice context tokens, minimum 4000 characters). This is not exact token counting. Ollama enforces the configured token window; very long or multilingual context can still be truncated. Older turns eventually fall out of context. No transcript is written to disk or stored between requests on the backend. Separate browser pages have separate transcripts; reload starts fresh. Failed, cancelled, or incomplete turns are not used as follow-up context by the frontend.

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
