"""Sequential, cancellable workflows over the existing permission-controlled registry."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

from backend.automation.history import ExecutionHistory
from backend.automation.models import WorkflowPlan
from backend.automation.policy import LOW_RISK, classify
from backend.automation.scheduler import WorkflowScheduler
from backend.automation.verification import verify
from backend.tools.registry import ToolError

TERMINAL = {'completed', 'failed', 'cancelled', 'blocked', 'expired'}


class AutomationEngine:
    def __init__(self, registry, history_path, scheduler=None):
        self.registry = registry
        self.history = ExecutionHistory(history_path)
        self.scheduler = scheduler if scheduler is not None else WorkflowScheduler()
        self.enabled = False
        self.automatic = set()
        self.revision = 0
        self.workflows = {}
        self.tasks = set()

    def policy(self):
        return {'enabled': self.enabled, 'automatic_tools': sorted(self.automatic),
                'eligible_automatic_tools': sorted(LOW_RISK), 'scheduler_available': self.scheduler.available()}

    def configure(self, enabled, automatic_tools, approved):
        if not approved:
            raise ToolError('Explicit workflow permission approval is required.', 403)
        if not set(automatic_tools).issubset(LOW_RISK):
            raise ToolError('Only system_info, list_directory and search_files may be automatic.', 403)
        self.revision += 1
        self.enabled = False
        for item in list(self.workflows.values()):
            if item['status'] not in TERMINAL:
                self.cancel(item['id'])
        self.automatic = set(automatic_tools) if enabled else set()
        self.enabled = enabled
        return self.policy()

    def _fresh(self, item):
        if not self.enabled or self.revision != item['_revision'] or self.registry.revision != item['_tool_revision']:
            raise ToolError('Workflow or tool permissions changed. Generate a new plan.', 409)
        for step in item['steps']:
            self.registry.validate(step['tool'], step['arguments'])

    def create(self, plan: WorkflowPlan):
        if not self.enabled:
            raise ToolError('Automation is disabled. Approve workflow permissions first.', 403)
        if len(self.workflows) >= 100:
            for key in [key for key, value in self.workflows.items() if value['status'] in TERMINAL]:
                del self.workflows[key]
            if len(self.workflows) >= 100:
                raise ToolError('Too many active workflows. Cancel unused plans.', 429)
        steps = []
        with self.registry.lock:
            revision = self.registry.revision
            for index, step in enumerate(plan.steps):
                category, arguments, error = classify(self.registry, step.tool, step.arguments, self.automatic)
                steps.append({'number': index + 1, 'tool': step.tool, 'arguments': arguments if arguments is not None else step.arguments,
                              'category': category, 'status': 'blocked' if category == 'blocked' else 'pending',
                              'result': None, 'verification': None, 'error': error, 'operation_id': None})
        blocked = any(step['category'] == 'blocked' for step in steps)
        confirmation = any(step['category'] == 'confirmation_required' for step in steps)
        item = {'id': str(uuid4()), 'outcome': plan.outcome, 'steps': steps,
                'status': 'blocked' if blocked else 'planned', 'requires_confirmation': confirmation,
                'created_at': datetime.now(timezone.utc).isoformat(), 'scheduled_for': None,
                'error': 'The entire plan is blocked; no steps will execute.' if blocked else None,
                '_revision': self.revision, '_tool_revision': revision,
                '_created': time.monotonic(), '_cancel': asyncio.Event(), '_operation': None}
        self.history.append(item, item['status'])
        self.workflows[item['id']] = item
        if blocked:
            self._skip(item)
        return self.view(item['id'])

    def view(self, workflow_id):
        if workflow_id not in self.workflows:
            raise ToolError('Workflow not found. Restart clears executable plans; metadata history is separate.', 404)
        item = self.workflows[workflow_id]
        snapshot = deepcopy({key: value for key, value in item.items() if not key.startswith('_')})
        snapshot['report'] = {
            'completed': [step['number'] for step in item['steps'] if step['status'] == 'completed'],
            'incomplete': [step['number'] for step in item['steps'] if step['status'] != 'completed']}
        return snapshot

    def list(self):
        return [self.view(key) for key in reversed(self.workflows)]

    @staticmethod
    def _skip(item):
        for step in item['steps']:
            if step['status'] == 'pending':
                step['status'] = 'skipped'

    def _finish(self, item, status, error=None):
        item['status'], item['error'] = status, error
        if status != 'completed':
            self._skip(item)
        try:
            self.history.append(item, status)
        except ToolError:
            item['error'] = (error + ' ' if error else '') + 'Final workflow history write failed; inspect session results.'

    async def start(self, workflow_id, approved=False):
        item = self.workflows.get(workflow_id)
        if item is None:
            raise ToolError('Workflow not found.', 404)
        if item['status'] not in {'planned', 'awaiting_confirmation'}:
            raise ToolError('Workflow is not awaiting execution. Replays are blocked.', 409)
        if time.monotonic() - item['_created'] > 300:
            self._finish(item, 'expired', 'Plan approval expired. Generate a new plan.')
            raise ToolError(item['error'], 409)
        self._fresh(item)
        if item['requires_confirmation'] and not approved:
            raise ToolError('Review and approve the full exact plan before execution.', 403)
        if any(not task.done() for task in self.tasks):
            raise ToolError('Another workflow is running. Wait or cancel it.', 429)
        if any(not task.done() for task in self.registry.tasks):
            raise ToolError('A computer tool is still running. Wait for it to finish.', 429)
        self.history.append(item, 'running')  # fail closed before executing anything
        item['status'] = 'running'
        task = asyncio.create_task(self._run(item))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return self.view(workflow_id)

    async def _run(self, item):
        step = None
        try:
            async with asyncio.timeout(180):
                for step in item['steps']:
                    if item['_cancel'].is_set():
                        return
                    self._fresh(item)
                    proposal = self.registry.propose(step['tool'], step['arguments'])
                    item['_operation'] = proposal['id']
                    step['operation_id'] = proposal['id']
                    await self.registry.execute(proposal['id'], expected_revision=item['_tool_revision'])
                    step['status'] = 'running'
                    deadline = time.monotonic() + 20
                    while True:
                        if item['_cancel'].is_set():
                            self.registry.cancel(proposal['id'])
                            step['status'] = 'cancelled'
                            return
                        self._fresh(item)
                        snapshot = self.registry.view(proposal['id'])
                        if snapshot['status'] != 'running' and not any(not task.done() for task in self.registry.tasks):
                            break
                        if time.monotonic() > deadline:
                            raise ToolError('Step exceeded its execution deadline. No following steps were started.', 504)
                        await asyncio.sleep(.03)
                    if snapshot['status'] != 'completed':
                        raise ToolError(snapshot['error'] or 'Tool action did not complete.')
                    good, explanation = verify(step['tool'], snapshot['result'])
                    step['verification'] = {'passed': good, 'detail': explanation}
                    if not good:
                        raise ToolError('Step result failed its tool-specific verification. Remaining steps were skipped.')
                    step['result'], step['status'] = snapshot['result'], 'completed'
                    item['_operation'] = None
                    self.history.append(item, 'step_completed')
                self._finish(item, 'completed')
        except (Exception, asyncio.CancelledError) as exc:
            if item['_operation']:
                self.registry.cancel(item['_operation'])
            if item['_cancel'].is_set() or isinstance(exc, asyncio.CancelledError):
                if step and step['status'] == 'running':
                    step['status'] = 'cancelled'
                if item['status'] != 'cancelled':
                    self._finish(item, 'cancelled', 'Workflow cancelled; completed actions were not undone.')
            else:
                message = str(exc) if isinstance(exc, ToolError) else 'Workflow failed or timed out. No following steps were executed.'
                if step and step['status'] != 'completed':
                    step['status'], step['error'] = 'failed', message
                self._finish(item, 'failed', message)
        finally:
            item['_operation'] = None

    def cancel(self, workflow_id):
        item = self.workflows.get(workflow_id)
        if item is None:
            raise ToolError('Workflow not found.', 404)
        if item['status'] not in TERMINAL:
            item['_cancel'].set()
            self.scheduler.remove(workflow_id)
            if item['_operation']:
                self.registry.cancel(item['_operation'])
            for step in item['steps']:
                if step['status'] == 'running':
                    step['status'] = 'cancelled'
            self._finish(item, 'cancelled', 'Workflow cancelled; completed actions were not undone.')
        return self.view(workflow_id)

    def schedule(self, workflow_id, when, approved):
        item = self.workflows.get(workflow_id)
        if item is None:
            raise ToolError('Workflow not found.', 404)
        if not approved:
            raise ToolError('Explicit approval is required for a future schedule.', 403)
        if item['status'] != 'planned' or time.monotonic() - item['_created'] > 300:
            raise ToolError('Only a fresh, unexecuted plan can be scheduled.', 409)
        if when.tzinfo is None or not datetime.now(timezone.utc) < when <= datetime.now(timezone.utc) + timedelta(days=7):
            raise ToolError('Choose a timezone-aware future time within seven days.', 422)
        self._fresh(item)
        if not self.scheduler.available():
            raise ToolError('APScheduler is not installed. Immediate workflows are available; scheduling needs approved installation.', 503)
        self.history.append(item, 'schedule_requested')
        try:
            self.scheduler.add(workflow_id, when, self._due, self._missed)
            item['status'], item['scheduled_for'] = 'scheduled', when.isoformat()
            self.history.append(item, 'scheduled')
        except Exception:
            self.scheduler.remove(workflow_id)
            self._finish(item, 'failed', 'The scheduler could not register or record this start. No workflow was scheduled.')
            raise ToolError(item['error'], 503)
        return self.view(workflow_id)

    async def _due(self, workflow_id):
        item = self.workflows.get(workflow_id)
        if item is None or item['status'] != 'scheduled':
            return
        try:
            self._fresh(item)
            item['_created'] = time.monotonic()
            if item['requires_confirmation']:
                item['status'] = 'awaiting_confirmation'
                self.history.append(item, 'awaiting_confirmation')
            else:
                item['status'] = 'planned'
                await self.start(workflow_id)
        except ToolError as exc:
            self._finish(item, 'failed', str(exc))

    def _missed(self, workflow_id):
        item = self.workflows.get(workflow_id)
        if item and item['status'] == 'scheduled':
            self._finish(item, 'failed', 'Scheduled start was missed or failed; it was not replayed.')

    async def close(self):
        for item in list(self.workflows.values()):
            if item['status'] not in TERMINAL:
                self.cancel(item['id'])
        self.scheduler.close()
        if self.tasks:
            _, pending = await asyncio.wait(list(self.tasks), timeout=2)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
