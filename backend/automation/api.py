"""Local workflow API reuses the tool session's origin and token protection."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from backend.automation.models import WorkflowPlan
from backend.tools.api import authorized
from backend.tools.registry import Inputs, ToolError

router = APIRouter(prefix='/automation', tags=['Automation'], dependencies=[Depends(authorized)])


class Permissions(Inputs):
    enabled: bool
    automatic_tools: list[str] = Field(default_factory=list, max_length=3)
    approved: bool


class Question(Inputs):
    question: str = Field(min_length=1, max_length=4000)


class Approval(Inputs):
    approved: bool = False


class Schedule(Inputs):
    # ISO timestamp parsed explicitly: strict input models otherwise reject JSON datetimes.
    when: str = Field(min_length=1, max_length=50)
    approved: bool


@router.get('/policy')
async def policy(request: Request):
    return request.app.state.automation.policy()


@router.put('/policy')
async def configure(body: Permissions, request: Request):
    return request.app.state.automation.configure(body.enabled, body.automatic_tools, body.approved)


@router.post('/plan')
async def plan(body: Question, request: Request):
    engine = request.app.state.automation
    if not engine.enabled or not request.app.state.tools.enabled:
        raise ToolError('Enable computer tools and approve workflow permissions first.', 403)
    if not body.question.strip():
        raise ToolError('Describe the requested outcome.', 422)
    lock = request.app.state.generation_lock
    if lock.locked():
        raise ToolError('The local model is busy. Wait for the current response.', 429)
    # A permission change while the model works must invalidate its generated plan.
    snapshot = (engine.revision, engine.registry.revision)
    async with lock:
        try:
            async with asyncio.timeout(request.app.state.settings.generation_timeout):
                selection = await request.app.state.assistant.brain.plan_workflow(body.question, engine.registry)
        except TimeoutError:
            raise ToolError('Workflow planning timed out. Nothing was executed.', 504)
    if snapshot != (engine.revision, engine.registry.revision):
        raise ToolError('Permissions changed during planning. Submit your request again.', 409)
    if selection is None:
        return {'workflow': None, 'message': 'The complete outcome could not be mapped to supported tools. Clarify it; nothing was executed.'}
    return {'workflow': engine.create(selection)}


@router.post('/plans')
async def explicit_plan(body: WorkflowPlan, request: Request):
    return request.app.state.automation.create(body)


@router.get('/workflows')
async def workflows(request: Request):
    return request.app.state.automation.list()


@router.get('/history')
async def history(request: Request):
    return request.app.state.automation.history.list()


@router.get('/workflows/{workflow_id}')
async def workflow(workflow_id: str, request: Request):
    return request.app.state.automation.view(workflow_id)


@router.post('/workflows/{workflow_id}/start')
async def start(workflow_id: str, body: Approval, request: Request):
    return await request.app.state.automation.start(workflow_id, body.approved)


@router.post('/workflows/{workflow_id}/cancel')
async def cancel(workflow_id: str, request: Request):
    return request.app.state.automation.cancel(workflow_id)


@router.post('/workflows/{workflow_id}/schedule')
async def schedule(workflow_id: str, body: Schedule, request: Request):
    try:
        when = datetime.fromisoformat(body.when.replace('Z', '+00:00'))
    except ValueError:
        raise ToolError('Use an ISO timestamp with an explicit timezone offset.', 422)
    return request.app.state.automation.schedule(workflow_id, when, body.approved)
