"""Dashboard-bound, session-token protected tool approvals and operation polling."""

import asyncio
from secrets import compare_digest
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from backend.tools.registry import Inputs, ToolError


def dashboard(request: Request):
    # Loopback binding alone does not protect against malicious web pages or DNS rebinding.
    host = request.url.hostname
    if host not in {'127.0.0.1', 'localhost', '::1'}:
        raise ToolError('Tools are available only through the localhost dashboard.', 403)
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            allowed = (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
                       and parsed.port in {5173, 4173, request.app.state.settings.port}
                       and not parsed.username and not parsed.password)
        except ValueError:
            allowed = False
        if not allowed:
            raise ToolError('Untrusted request origin.', 403)
    if request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
        raise ToolError('Use a same-origin dashboard connection.', 403)


def authorized(request: Request):
    dashboard(request)
    if not compare_digest(request.headers.get('x-jarvis-tool-token', ''), request.app.state.tool_token):
        raise ToolError('Tool session expired. Refresh the dashboard.', 403)


router = APIRouter(prefix='/tools', tags=['Computer tools'], dependencies=[Depends(dashboard)])


class Permissions(Inputs):
    approved: bool
    enabled: bool
    directories: list[str] = Field(default_factory=list, max_length=8)
    applications: list[str] = Field(default_factory=list, max_length=2)
    websites: list[str] = Field(default_factory=list, max_length=12)


class Proposal(Inputs):
    tool: str = Field(min_length=1, max_length=50)
    arguments: dict = Field(default_factory=dict)


class Approval(Inputs):
    approved: bool


class Plan(Inputs):
    question: str = Field(min_length=1, max_length=4000)


@router.get('/session')
async def session(request: Request):
    return {'token': request.app.state.tool_token, 'catalog': request.app.state.tools.catalog()}


@router.get('/policy', dependencies=[Depends(authorized)])
async def policy(request: Request):
    return request.app.state.tools.policy()


@router.put('/policy', dependencies=[Depends(authorized)])
async def configure(body: Permissions, request: Request):
    if not body.approved:
        raise ToolError('Explicit approval is required to change tool permissions.', 403)
    return request.app.state.tools.configure(body.enabled, body.directories, body.applications, body.websites)


@router.post('/proposals', dependencies=[Depends(authorized)])
async def propose(body: Proposal, request: Request):
    return request.app.state.tools.propose(body.tool, body.arguments)


@router.post('/plan', dependencies=[Depends(authorized)])
async def plan(body: Plan, request: Request):
    registry = request.app.state.tools
    if not registry.enabled:
        raise ToolError('Enable tools and approve session permissions first.', 403)
    lock = request.app.state.generation_lock
    if lock.locked():
        raise ToolError('The model is busy. Wait for the current response.', 429)
    async with lock:
        try:
            async with asyncio.timeout(request.app.state.settings.generation_timeout):
                selection = await request.app.state.assistant.brain.select_tool(body.question, registry)
        except TimeoutError:
            raise ToolError('Tool selection timed out. No action was executed.', 504)
    if selection is None:
        return {'proposal': None, 'message': 'No safe, unambiguous approved tool was selected. Use the manual tool controls or clarify your request.'}
    return {'proposal': registry.propose(selection['tool'], selection['arguments'])}


@router.post('/operations/{job_id}/execute', dependencies=[Depends(authorized)])
async def execute(job_id: str, body: Approval, request: Request):
    if not body.approved:
        raise ToolError('Review and approve this exact action first.', 403)
    return await request.app.state.tools.execute(job_id)


@router.post('/operations/{job_id}/cancel', dependencies=[Depends(authorized)])
async def cancel(job_id: str, request: Request):
    return request.app.state.tools.cancel(job_id)


@router.get('/operations/{job_id}', dependencies=[Depends(authorized)])
async def operation(job_id: str, request: Request):
    return request.app.state.tools.view(job_id)


@router.get('/activity', dependencies=[Depends(authorized)])
async def activity(request: Request):
    with request.app.state.tools.lock:
        return list(request.app.state.tools.events)
