"""Explicit local memory approval and management API."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/memory", tags=["Memory"], dependencies=[Depends(no_cache)])


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    save_history: bool = False
    approved: bool = False
    recall_history: bool = False


class AssistantStyle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tone: Literal['professional', 'friendly', 'formal'] = 'professional'
    detail: Literal['balanced', 'concise', 'detailed'] = 'balanced'


class ApprovedStyle(AssistantStyle):
    approved: bool = False


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["preference", "project", "fact"]
    content: str = Field(min_length=1, max_length=2000)
    approved: bool = False

    @field_validator("content")
    @classmethod
    def nonblank(cls, text):
        if not text.strip():
            raise ValueError("Memory cannot be blank")
        return text


@router.get("/settings")
def settings(request: Request):
    return request.app.state.memory.settings()


@router.put("/settings")
def configure(body: MemorySettings, request: Request):
    return request.app.state.memory.configure(body.enabled, body.save_history, body.approved, body.recall_history)


@router.get('/personality')
def personality(request: Request):
    return request.app.state.memory.personality()


@router.put('/personality')
def save_personality(body: ApprovedStyle, request: Request):
    return request.app.state.memory.save_personality(body.model_dump(exclude={'approved'}), body.approved)


@router.get("/entries")
def entries(request: Request, q: str = Query("", max_length=200)):
    return request.app.state.memory.list_memories(q)


@router.post("/entries", status_code=201)
def save(body: MemoryEntry, request: Request):
    return request.app.state.memory.save(body.kind, body.content, body.approved)


@router.put("/entries/{memory_id}")
def edit(memory_id: int, body: MemoryEntry, request: Request):
    return request.app.state.memory.save(body.kind, body.content, body.approved, memory_id)


@router.delete("/entries/{memory_id}")
def delete(memory_id: int, request: Request, confirm: bool = False):
    request.app.state.memory.delete("memories", memory_id, confirm)
    return {"deleted": True}


@router.get("/conversations")
def conversations(request: Request, q: str = Query("", max_length=200), conversation_id: UUID | None = None):
    return request.app.state.memory.conversations(q, str(conversation_id) if conversation_id else None)


@router.delete("/conversations/{turn_id}")
def delete_turn(turn_id: UUID, request: Request, confirm: bool = False):
    request.app.state.memory.delete("turns", str(turn_id), confirm)
    return {"deleted": True}
