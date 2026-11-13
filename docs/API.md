# JARVIS Local API v0.1.0

Start with `python -m backend.main` using the project virtual environment. Default base URL: `http://127.0.0.1:8000`. No AI, voice, or computer control is connected.

| Method | Path | Result |
| --- | --- | --- |
| GET | /health | HTTP 200 backend liveness |
| GET | /docs | Self-contained HTML documentation without external resources |
| GET | /openapi.json | Generated OpenAPI schema |

Health response:

```json
{"status":"ok","service":"JARVIS","ai_connected":false}
```

Liveness does not imply model readiness. No AI model is connected.

Error envelope:

```json
{"error":{"code":"http_404","message":"Not Found"}}
```

Unknown routes return 404. Unsupported methods return 405 with the Allow header. Invalid request data returns 422 with code `validation_error` and message `Invalid request data`. Unexpected failures return 500 with code `internal_error` and message `Internal server error`. Internal exception details are logged locally and not returned. Health takes no parameters; validation handling is exercised through a test-only route.

Implementation references: official FastAPI [error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/) and [testing](https://fastapi.tiangolo.com/tutorial/testing/) guidance, and [Uvicorn settings](https://uvicorn.dev/settings/). The launcher explicitly binds to loopback and disables proxy-header interpretation.
