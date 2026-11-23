"""Explicit local dashboard API. Google writes are not available to automatic workflows."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from backend.integrations.google.common import GoogleError
from backend.integrations.google.models import EventInput, MailInput
from backend.tools.api import authorized
from backend.tools.registry import Inputs

Service = Literal['calendar', 'gmail', 'classroom']
router = APIRouter(prefix='/integrations/google', tags=['Google integrations'], dependencies=[Depends(authorized)])


class Capabilities(Inputs):
    approved: bool
    enabled: bool
    write: bool = False
    send: bool = False
    role: Literal['student', 'teacher'] = 'student'


class Approval(Inputs):
    approved: bool


@router.get('/status')
async def status(request: Request):
    return request.app.state.google.auth.status()


@router.put('/{service}/settings')
async def settings(service: Service, body: Capabilities, request: Request):
    manager = request.app.state.google
    result = await manager.auth.configure(service, body.enabled, body.write, body.send, body.role, body.approved)
    manager.invalidate(service)
    return result


@router.post('/{service}/connect')
async def connect(service: Service, body: Approval, request: Request):
    if not body.approved:
        raise GoogleError('Approve opening Google OAuth consent for these scopes.', 403)
    request.app.state.google.invalidate(service)
    return await request.app.state.google.auth.begin(service)


@router.post('/{service}/cancel-auth')
async def cancel_auth(service: Service, request: Request):
    await request.app.state.google.auth.cancel_auth(service)
    return {'status': 'cancelled'}


@router.post('/{service}/disconnect')
async def disconnect(service: Service, body: Approval, request: Request):
    if not body.approved:
        raise GoogleError('Confirm disconnecting and forgetting local authorization.', 403)
    manager = request.app.state.google
    result = await manager.auth.disconnect(service)
    manager.invalidate(service)
    return result


@router.get('/calendar/events')
async def events(request: Request):
    return await request.app.state.google.adapters['calendar'].upcoming()


@router.post('/calendar/proposals')
async def event_proposal(body: EventInput, request: Request):
    return await request.app.state.google.propose('calendar', 'create_event', body.model_dump())


@router.get('/gmail/messages')
async def messages(request: Request, q: str = Query(default='', max_length=500), page_token: str | None = Query(default=None, max_length=2000)):
    return await request.app.state.google.adapters['gmail'].search(q, page_token)


@router.get('/gmail/messages/{message_id}')
async def message(message_id: str, request: Request):
    return await request.app.state.google.adapters['gmail'].read(message_id)


@router.get('/gmail/threads/{thread_id}')
async def thread(thread_id: str, request: Request):
    return await request.app.state.google.adapters['gmail'].thread(thread_id)


@router.post('/gmail/threads/{thread_id}/summarize')
async def summarize(thread_id: str, body: Approval, request: Request):
    if not body.approved:
        raise GoogleError('Approve sending this selected conversation to local Ollama for summarization.', 403)
    lock = request.app.state.generation_lock
    if lock.locked():
        raise GoogleError('The local model is busy. Try after the current generation.', 429)
    async with lock:
        revision = request.app.state.google.auth.require('gmail')['revision']
        content = await request.app.state.google.adapters['gmail'].thread(thread_id)
        try:
            async with asyncio.timeout(request.app.state.settings.generation_timeout):
                summary = await request.app.state.assistant.brain.summarize_email(content)
        except TimeoutError:
            raise GoogleError('Local email summarization timed out. No email was sent or saved.', 504)
        if request.app.state.google.auth.require('gmail')['revision'] != revision:
            raise GoogleError('Gmail permissions changed during summarization; the result was discarded.', 409)
    return {'summary': summary, 'source': 'local_model', 'truncated': content['truncated']}


@router.post('/gmail/proposals/{action}')
async def mail_proposal(action: Literal['create_draft', 'send_message'], body: MailInput, request: Request):
    return await request.app.state.google.propose('gmail', action, body.model_dump())


@router.get('/classroom/courses')
async def courses(request: Request, page_token: str | None = Query(default=None, max_length=2000)):
    return await request.app.state.google.adapters['classroom'].courses(page_token)


@router.get('/classroom/courses/{course_id}/assignments')
async def assignments(course_id: str, request: Request, page_token: str | None = Query(default=None, max_length=2000)):
    return await request.app.state.google.adapters['classroom'].assignments(course_id, page_token)


@router.get('/proposals/{proposal_id}')
async def proposal(proposal_id: str, request: Request):
    return request.app.state.google.view(proposal_id)


@router.post('/proposals/{proposal_id}/execute')
async def execute(proposal_id: str, body: Approval, request: Request):
    return await request.app.state.google.execute(proposal_id, body.approved)


@router.post('/proposals/{proposal_id}/cancel')
async def cancel(proposal_id: str, request: Request):
    return request.app.state.google.cancel(proposal_id)
