"""Local JARVIS HTTP API. Start from the repository root with python -m backend.main."""

import logging
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from uuid import UUID
from contextlib import aclosing, asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.exceptions import HTTPException

from backend.config import Settings
from backend.core.assistant import Assistant
from backend.core.brain import Brain
from backend.core.providers import ModelError, ModelProvider
from backend.integrations.provider_factory import create_provider
from backend.voice.api import VoiceService, router as voice_router
from backend.voice.config import VoiceSettings
from backend.voice.tts import SpeechService, SpeechSettings, router as speech_router
from backend.memory.manager import MemoryManager, MemoryError
from backend.memory.api import router as memory_router, AssistantStyle
from backend.tools.registry import ToolRegistry, ToolError
from backend.tools.api import router as tools_router
from secrets import token_urlsafe

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["JARVIS"]
    ai_connected: bool
    provider: str
    model: str
    ai_status: str
    ai_message: str


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=41)
    save_history: bool = False
    conversation_id: UUID | None = None
    turn_id: UUID | None = None
    context_summary: str = Field(default='', max_length=5000)
    assistant_preferences: AssistantStyle | None = None

    @model_validator(mode="after")
    def conversation_order(self):
        for index, message in enumerate(self.messages):
            if message.role != ("user" if index % 2 == 0 else "assistant"):
                raise ValueError("Messages must alternate user/assistant, starting with user")
            if message.role == "user" and len(message.content) > 4000:
                raise ValueError("User messages have a 4000-character limit")
        if self.messages[-1].role != "user":
            raise ValueError("The final message must be a user question")
        if sum(len(message.content) for message in self.messages) > 40000:
            raise ValueError("Conversation request is too large")
        if self.save_history and (self.conversation_id is None or self.turn_id is None):
            raise ValueError("Saving history requires conversation_id and turn_id")
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def create_app(settings: Settings | None = None, provider: ModelProvider | None = None,
               memory: MemoryManager | None = None, tools: ToolRegistry | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        manager = memory if memory is not None else MemoryManager(
            Path(os.environ.get("JARVIS_MEMORY_DB", str(Path(__file__).resolve().parents[1] / "data" / "memory.sqlite3"))),
            allowed=os.environ.get("JARVIS_MEMORY_ALLOWED", "1") != "0")
        application.state.memory = manager
        application.state.tools = tools if tools is not None else ToolRegistry(
            Path(__file__).resolve().parents[1] / 'data' / 'tool-audit.jsonl')
        application.state.tool_token = token_urlsafe(32)
        brain = Brain(settings, provider if provider is not None else create_provider(settings), manager)
        application.state.assistant = Assistant(brain)
        application.state.generation_lock = asyncio.Lock()
        application.state.voice = VoiceService(VoiceSettings.from_env())
        application.state.speech = SpeechService(SpeechSettings.from_env())
        try:
            yield
        finally:
            application.state.tools.close()
            application.state.voice.close()
            application.state.speech.close()
            await brain.provider.close()

    application = FastAPI(
        title="JARVIS Local API",
        version="0.7.0",
        description="Local chat, optional voice/memory, and opt-in permission-controlled computer tools.",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        responses={500: {"model": ErrorResponse, "description": "Unexpected server error"}},
    )
    application.state.settings = settings
    application.include_router(voice_router)
    application.include_router(speech_router)
    application.include_router(memory_router)
    application.include_router(tools_router)

    @application.middleware('http')
    async def tool_response_privacy(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/tools'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @application.exception_handler(ToolError)
    async def tool_error(request: Request, exc: ToolError):
        return JSONResponse(status_code=exc.status, content={'error': {'code': 'tool_error', 'message': str(exc)}})

    @application.exception_handler(MemoryError)
    async def memory_error(request: Request, exc: MemoryError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": "memory_error", "message": str(exc)}})

    @application.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        return JSONResponse(status_code=503, content={"error": {"code": "memory_unavailable", "message": "Local memory storage is unavailable. Check the database path and file permissions."}})

    @application.exception_handler(ModelError)
    async def model_error(request: Request, exc: ModelError):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": exc.code, "message": str(exc)}})

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}},
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Invalid request data"}},
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )

    @application.get("/health", response_model=HealthResponse, tags=["System"],
                     summary="Check backend liveness")
    async def health(request: Request):
        return await request.app.state.assistant.health()

    @application.post("/chat", tags=["Conversation"], summary="Stream a local AI reply",
                      responses={200: {"content": {"application/x-ndjson": {"schema": {"type": "string"}}}},
                                 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
                                 429: {"model": ErrorResponse}})
    async def chat(body: ChatRequest, request: Request):
        assistant = request.app.state.assistant
        readiness = await assistant.brain.provider.status()
        if not readiness.ready:
            raise ModelError(readiness.code, readiness.message)
        if application.state.generation_lock.locked():
            raise ModelError("model_busy", "JARVIS is answering another request. Please try again.", 429)

        async def events():
            def encode(event):
                return json.dumps(event, ensure_ascii=False) + "\n"

            acquired = False
            answer = []
            try:
                # One local generation at a time protects the 6 GiB GPU from overlap.
                try:
                    await asyncio.wait_for(application.state.generation_lock.acquire(), timeout=0.1)
                    acquired = True
                except TimeoutError:
                    raise ModelError("model_busy", "JARVIS is answering another request. Please try again.", 429)
                async with asyncio.timeout(settings.generation_timeout):
                    async with aclosing(assistant.brain.stream([item.model_dump() for item in body.messages],
                        summary=body.context_summary,
                        preferences=body.assistant_preferences.model_dump() if body.assistant_preferences else None,
                        conversation_id=str(body.conversation_id) if body.conversation_id else None)) as stream:
                        async for content in stream:
                            if body.save_history:
                                answer.append(content)
                            yield encode({"type": "delta", "content": content})
                if body.save_history:
                    try:
                        memory_status = application.state.memory.save_turn(str(body.conversation_id), str(body.turn_id), body.messages[-1].content, "".join(answer))
                    except (sqlite3.Error, MemoryError):
                        memory_status = "error"
                    yield encode({"type": "memory", "status": memory_status})
                yield encode({"type": "done", "model": settings.model})
            except TimeoutError:
                yield encode({"type": "error", "error": {"code": "generation_timeout",
                             "message": "Generation exceeded its time limit. Try a shorter prompt or a smaller installed model."}})
            except ModelError as exc:
                yield encode({"type": "error", "error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                logger.exception("Chat stream failed")
                yield encode({"type": "error", "error": {"code": "internal_error", "message": "The response could not be completed."}})
            finally:
                if acquired:
                    application.state.generation_lock.release()

        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def documentation():
        # Self-contained documentation avoids third-party CDN requests.
        return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>JARVIS API documentation</title><main><h1>JARVIS Local API v0.7.0</h1>
<p>Local Ollama conversations, opt-in voice, memory and restricted computer tools. No automatic downloads.</p>
<h2>Computer tools</h2><p>GET /tools/session returns the session token and JSON-schema catalog to the local dashboard.
All other /tools routes require X-Jarvis-Tool-Token and a trusted local origin/Host. PUT /tools/policy requires approved=true;
permissions reset on restart. POST /tools/proposals validates one tool; POST /tools/plan uses Ollama to propose one.
No proposal executes automatically. POST /tools/operations/{id}/execute requires approved=true;
GET /tools/operations/{id} polls results; POST /tools/operations/{id}/cancel cancels pending/running work.
GET /tools/activity returns metadata only. Tool responses use no-store. See docs/TOOLS.md for limits and audit details.</p>
<h2>Conversation and personalization</h2><p>Chat may include context_summary (temporary extractive quotes, maximum 5000 characters)
and assistant_preferences (tone: professional/friendly/formal; detail: balanced/concise/detailed).
GET/PUT /memory/personality views or explicitly approves a saved style; memory must be enabled for persistent writes.
Memory settings include a separate recall_history permission, off by default. Archive excerpts are retrieved only for references to earlier chats.
Summaries and old AI answers are treated as unverified reference data, never automatically saved as facts.
See docs/CONVERSATION.md for context limits and tests.</p>
<h2>Memory</h2><p>Memory and conversation saving default off. GET/PUT /memory/settings manage explicit enablement and history consent.
GET/POST /memory/entries list/search or approve a preference/project/fact; PUT/DELETE /memory/entries/{id} edit/delete.
GET /memory/conversations searches saved exchanges; DELETE /memory/conversations/{turn_id} deletes one.
Saving/editing requires approved=true. Deletion requires confirm=true. Known sensitive patterns are blocked, but detection is not infallible.
Chat requests may opt into saving the new completed pair with save_history=true and UUID conversation_id/turn_id.
The stream then includes a memory status event before done. Saved approved entries may be retrieved as reference; archives stay separate from temporary context.
See docs/MEMORY.md for storage/privacy details.</p>
<h2>Speech output</h2><p>GET /speech/status checks Piper and local voice assets without synthesis.
POST /speech/synthesize accepts a text object (1 to 1000 nonblank characters) and returns in-memory audio/wav with Cache-Control: no-store.
Missing assets return 503, a busy native worker returns 429, synthesis failures return 502, and a generation deadline returns 504.
Playback, device selection, pause/resume, interruption, and volume/speed controls are owned by the local browser.
See docs/SPEECH_OUTPUT.md for setup and actual-inference limitations.</p>
<h2>Voice</h2><p>GET /voice/status reports local dependency/asset readiness without loading models.
WebSocket /voice/listen requires a local dashboard Origin and an initial consent=true message with mode manual or wake.
Audio is mono PCM16 at 16kHz, exactly 1280 samples per frame. Server events: state, transcript, no_speech, error.
Controls: finish (transcribe current utterance), stop (discard and close), resume (wake mode after chat).
All audio remains in bounded memory; no audio files are saved. See docs/VOICE_SETUP.md in the repository.</p>
<h2>GET /health</h2><p>Backend liveness. Returns HTTP 200:</p>
<p>Includes ai_connected, provider, model, ai_status, and ai_message. AI readiness means the local service is reachable and the selected model is installed; not that inference has been verified.</p>
<p><a href="/health">Open health check</a></p>
<h2>POST /chat</h2><p>Send alternating user/assistant history ending with a user message.
The system personality is added by the server. Recent complete turns are retained within a bounded context budget.</p>
<pre>{"messages":[{"role":"user","content":"Hello JARVIS"}]}</pre>
<p>Returns newline-delimited JSON events: delta (content), done (model), or error (error.code and error.message).
Missing service/model returns HTTP 503 before streaming. A failure after streaming begins is an error event.
User messages have a 4000-character limit (assistant history: 16000); maximum 41 messages and 40000 total characters.
Temporary context lives in the browser session. SQLite stores only explicitly approved memories and opted-in completed exchanges.</p>
<h2>Errors</h2><p>HTTP errors use an error object containing code and message.
404: unknown route; 405: unsupported method; 422: invalid request;
500: unexpected server error. Internal exception details are not returned.</p>
<pre>{"error":{"code":"http_404","message":"Not Found"}}</pre>
<p><a href="/openapi.json">OpenAPI JSON schema</a></p></main></html>"""

    return application


app = create_app()


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port,
                log_level=settings.log_level, proxy_headers=False)


if __name__ == "__main__":
    main()
