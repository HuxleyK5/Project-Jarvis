"""Workflow safety and observable execution tests; no real launch effects or AI required."""

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.automation.engine import AutomationEngine
from backend.automation.history import ExecutionHistory
from backend.automation.models import WorkflowPlan
from backend.automation.scheduler import WorkflowScheduler
from backend.config import Settings
from backend.core.brain import Brain
from backend.main import create_app
from backend.tests.test_tools import SelectionProvider
from backend.tools.registry import ToolError, ToolRegistry


class TestScheduler:
    def __init__(self, available=True):
        self.entries = {}
        self.installed = available

    def available(self):
        return self.installed

    def add(self, key, when, callback, missed):
        self.entries[key] = (when, callback, missed)

    def remove(self, key):
        self.entries.pop(key, None)

    def close(self):
        self.entries.clear()


class AutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'data')
        self.base = Path(self.temp.name)
        self.folder = self.base / 'selected'
        self.folder.mkdir()
        (self.folder / 'notes.md').write_text('Synthetic workflow document.', encoding='utf-8')
        self.registry = ToolRegistry(self.base / 'tool-audit.jsonl')
        self.registry.configure(True, [str(self.folder)], ['notepad'], ['https://example.org/'])
        self.root = next(iter(self.registry.roots))
        self.scheduler = TestScheduler()
        self.engine = AutomationEngine(self.registry, self.base / 'workflow-history.jsonl', self.scheduler)
        self.engine.configure(True, ['system_info', 'list_directory', 'search_files'], True)

    async def asyncTearDown(self):
        await self.engine.close()
        if self.registry.tasks:
            await asyncio.gather(*list(self.registry.tasks), return_exceptions=True)
        self.temp.cleanup()

    def plan(self, *steps):
        return self.engine.create(WorkflowPlan(outcome='Synthetic test outcome', steps=list(steps)))

    async def run_plan(self, plan, approved=False):
        await self.engine.start(plan['id'], approved)
        if self.engine.tasks:
            await asyncio.gather(*list(self.engine.tasks))
        return self.engine.view(plan['id'])

    async def test_sequential_real_read_only_steps_and_report(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}}, {'tool': 'list_directory', 'arguments': {'root': self.root}},
                         {'tool': 'search_files', 'arguments': {'root': self.root, 'query': 'notes'}})
        self.assertFalse(plan['requires_confirmation'])
        self.assertEqual(plan['status'], 'planned')
        self.assertEqual(len(self.registry.jobs), 0)
        result = await self.run_plan(plan)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['report'], {'completed': [1, 2, 3], 'incomplete': []})
        self.assertTrue(all(step['verification']['passed'] for step in result['steps']))
        events = [json.loads(line) for line in self.registry.audit_path.read_text().splitlines()]
        running = [event['tool'] for event in events if event['status'] == 'running']
        self.assertEqual(running, ['system_info', 'list_directory', 'search_files'])

    async def test_document_read_requires_confirmation(self):
        plan = self.plan({'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'notes.md'}})
        self.assertEqual(plan['steps'][0]['category'], 'confirmation_required')
        with self.assertRaises(ToolError):
            await self.engine.start(plan['id'], False)
        self.assertEqual(len(self.registry.jobs), 0)
        result = await self.run_plan(plan, True)
        self.assertEqual(result['steps'][0]['result']['text'], 'Synthetic workflow document.')

    async def test_blocked_whole_plan_never_runs_safe_prefix(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}}, {'tool': 'shell', 'arguments': {'command': 'never'}})
        self.assertEqual(plan['status'], 'blocked')
        self.assertEqual(plan['steps'][0]['status'], 'skipped')
        with self.assertRaises(ToolError):
            await self.engine.start(plan['id'], True)
        self.assertFalse(self.registry.jobs)

    async def test_unapproved_paths_and_applications_are_blocked(self):
        for tool, args in [('read_text', {'root': self.root, 'path': '../outside.txt'}),
                           ('open_application', {'application': 'powershell'}),
                           ('open_website', {'website': 'unapproved'})]:
            plan = self.plan({'tool': tool, 'arguments': args})
            self.assertEqual(plan['status'], 'blocked')

    async def test_risk_escalation_and_no_approval_rejected(self):
        with self.assertRaises(ToolError):
            self.engine.configure(True, ['open_application'], True)
        with self.assertRaises(ToolError):
            self.engine.configure(True, [], False)
        self.engine.configure(True, [], True)
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.assertTrue(plan['requires_confirmation'])

    async def test_failure_stops_following_steps_and_reports_prefix(self):
        (self.folder / 'secret.txt').write_text('password: synthetic', encoding='utf-8')
        plan = self.plan({'tool': 'system_info', 'arguments': {}},
                         {'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'secret.txt'}},
                         {'tool': 'list_directory', 'arguments': {'root': self.root}})
        result = await self.run_plan(plan, True)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['report'], {'completed': [1], 'incomplete': [2, 3]})
        self.assertEqual(result['steps'][2]['status'], 'skipped')
        self.assertEqual(len(self.registry.jobs), 2)

    async def test_malformed_tool_result_fails_verification(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}}, {'tool': 'system_info', 'arguments': {}})
        with patch.object(self.registry, '_perform', return_value={'not': 'a real result'}):
            result = await self.run_plan(plan)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['steps'][0]['verification']['passed'])
        self.assertEqual(len(self.registry.jobs), 1)

    async def test_launch_confirmation_reports_only_handoff(self):
        plan = self.plan({'tool': 'open_application', 'arguments': {'application': 'notepad'}})
        self.assertTrue(plan['requires_confirmation'])
        with patch('backend.tools.registry.subprocess.Popen'):
            result = await self.run_plan(plan, True)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('unverified', result['steps'][0]['verification']['detail'])

    async def test_replay_and_expiry(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        await self.run_plan(plan)
        with self.assertRaises(ToolError):
            await self.engine.start(plan['id'])
        second = self.plan({'tool': 'system_info', 'arguments': {}})
        self.engine.workflows[second['id']]['_created'] -= 301
        with self.assertRaises(ToolError):
            await self.engine.start(second['id'])
        self.assertEqual(self.engine.view(second['id'])['status'], 'expired')

    async def test_tool_permission_revision_invalidates_even_system_only_plan(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.registry.configure(True, [], [], [])
        with self.assertRaises(ToolError):
            await self.engine.start(plan['id'])
        self.assertFalse(self.registry.jobs)

    async def test_cancellation_running_discards_result_and_stops_next_step(self):
        started, released = threading.Event(), threading.Event()
        def work(name, args, cancel):
            started.set()
            released.wait(2)
            return {}
        plan = self.plan({'tool': 'system_info', 'arguments': {}}, {'tool': 'system_info', 'arguments': {}})
        with patch.object(self.registry, '_perform', side_effect=work):
            await self.engine.start(plan['id'])
            await asyncio.to_thread(started.wait, 1)
            self.engine.cancel(plan['id'])
            released.set()
            await asyncio.gather(*list(self.engine.tasks))
        result = self.engine.view(plan['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['steps'][1]['status'], 'skipped')
        self.assertEqual(len(self.registry.jobs), 1)

    async def test_disable_cancels_and_blocks_new_plans(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.engine.configure(False, [], True)
        self.assertEqual(self.engine.view(plan['id'])['status'], 'cancelled')
        with self.assertRaises(ToolError):
            self.plan({'tool': 'system_info', 'arguments': {}})

    async def test_history_persists_without_documents_requests_or_paths(self):
        plan = self.plan({'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'notes.md'}})
        await self.run_plan(plan, True)
        text = self.engine.history.path.read_text()
        for excluded in ['notes.md', str(self.folder), 'Synthetic workflow document', 'Synthetic test outcome']:
            self.assertNotIn(excluded, text)
        reopened = ExecutionHistory(self.engine.history.path)
        self.assertEqual(reopened.list()[0]['status'], 'completed')
        replacement = AutomationEngine(self.registry, self.engine.history.path, TestScheduler())
        self.assertFalse(replacement.enabled)
        self.assertFalse(replacement.workflows)
        self.assertEqual(replacement.history.list()[0]['completed'], 1)

    async def test_history_failure_blocks_execution(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        with patch.object(self.engine.history, 'append', side_effect=ToolError('unavailable', 503)):
            with self.assertRaises(ToolError):
                await self.engine.start(plan['id'])
        self.assertFalse(self.registry.jobs)

    async def test_automatic_scheduled_workflow_revalidates_then_runs(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.assertEqual(self.engine.view(plan['id'])['status'], 'scheduled')
        self.assertFalse(self.registry.jobs)
        await self.engine._due(plan['id'])
        await asyncio.gather(*list(self.engine.tasks))
        self.assertEqual(self.engine.view(plan['id'])['status'], 'completed')

    async def test_significant_scheduled_workflow_waits_for_fresh_confirmation(self):
        plan = self.plan({'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'notes.md'}})
        self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        await self.engine._due(plan['id'])
        self.assertEqual(self.engine.view(plan['id'])['status'], 'awaiting_confirmation')
        self.assertFalse(self.registry.jobs)
        result = await self.run_plan(plan, True)
        self.assertEqual(result['status'], 'completed')

    async def test_schedule_validation_missing_scheduler_and_cancel(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        for when, approved in [(datetime.now(), True), (datetime.now(timezone.utc) - timedelta(seconds=1), True),
                               (datetime.now(timezone.utc) + timedelta(days=8), True), (datetime.now(timezone.utc) + timedelta(minutes=1), False)]:
            with self.assertRaises(ToolError):
                self.engine.schedule(plan['id'], when, approved)
        self.scheduler.installed = False
        with self.assertRaises(ToolError):
            self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.scheduler.installed = True
        self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.engine.cancel(plan['id'])
        self.assertFalse(self.scheduler.entries)

    async def test_missed_schedule_does_not_replay(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.engine._missed(plan['id'])
        self.assertEqual(self.engine.view(plan['id'])['status'], 'failed')
        self.assertFalse(self.registry.jobs)

    async def test_scheduled_permissions_revoked_before_due_never_execute(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.registry.configure(False, [], [], [])
        await self.engine._due(plan['id'])
        self.assertEqual(self.engine.view(plan['id'])['status'], 'failed')
        self.assertFalse(self.registry.jobs)

    async def test_failed_schedule_registration_does_not_report_armed_job(self):
        plan = self.plan({'tool': 'system_info', 'arguments': {}})
        with patch.object(self.scheduler, 'add', side_effect=RuntimeError('private internal detail')):
            with self.assertRaises(ToolError):
                self.engine.schedule(plan['id'], datetime.now(timezone.utc) + timedelta(minutes=1), True)
        self.assertEqual(self.engine.view(plan['id'])['status'], 'failed')
        self.assertFalse(self.scheduler.entries)
        self.assertNotIn('private internal', self.engine.history.path.read_text())

    async def test_only_one_workflow_worker_can_run(self):
        first = self.plan({'tool': 'system_info', 'arguments': {}})
        second = self.plan({'tool': 'system_info', 'arguments': {}})
        await self.engine.start(first['id'])
        with self.assertRaises(ToolError):
            await self.engine.start(second['id'])
        await asyncio.gather(*list(self.engine.tasks))

    async def test_brain_builds_plan_without_executing(self):
        raw = {'outcome': 'Check system twice', 'steps': [{'tool': 'system_info', 'arguments': {}}] * 2}
        provider = SelectionProvider(json.dumps(raw))
        result = await Brain(Settings(), provider).plan_workflow('Check my system twice', self.registry)
        self.assertEqual(len(result.steps), 2)
        self.assertFalse(self.registry.jobs)
        self.assertIn('Never claim completion', provider.requests[0][0]['content'])

    async def test_model_cannot_inject_risk_flags_commands_or_invalid_json(self):
        for raw in ['bad', '{"outcome":"test","steps":[{"tool":"system_info","arguments":{},"category":"automatic"}]}',
                    '{"outcome":"test","steps":[]}']:
            with self.assertRaises(ToolError):
                await Brain(Settings(), SelectionProvider(raw)).plan_workflow('test', self.registry)
        with self.assertRaises(ValidationError):
            WorkflowPlan(outcome='test', steps=[{'tool': 'system_info', 'arguments': {}}] * 9)

    async def test_document_path_must_be_explicit_in_model_request(self):
        raw = {'outcome': 'Read notes', 'steps': [{'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'notes.md'}}]}
        provider = SelectionProvider(json.dumps(raw))
        with self.assertRaises(ToolError):
            await Brain(Settings(), provider).plan_workflow('Read something', self.registry)

    @unittest.skipUnless(importlib.util.find_spec('apscheduler') is not None, 'APScheduler installation not authorized/available')
    async def test_real_apscheduler_fires_one_time_coroutine(self):
        adapter = WorkflowScheduler()
        fired = asyncio.Event()
        async def callback(workflow_id):
            self.assertEqual(workflow_id, 'test-job')
            fired.set()
        try:
            adapter.add('test-job', datetime.now(timezone.utc) + timedelta(milliseconds=150), callback, lambda key: None)
            await asyncio.wait_for(fired.wait(), 3)
        finally:
            adapter.close()


class AutomationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.registry = ToolRegistry(Path(self.temp) / 'tool-audit.jsonl')
        provider = SelectionProvider('{"outcome":"Check workstation","steps":[{"tool":"system_info","arguments":{}}]}')
        self.app = create_app(Settings(), provider, tools=self.registry)
        self.client = self.enterContext(TestClient(self.app, base_url='http://127.0.0.1:8000'))
        self.headers = {'X-Jarvis-Tool-Token': self.client.get('/tools/session').json()['token']}
        self.registry.configure(True, [], [], [])

    def test_default_off_and_http_request_protection(self):
        self.assertEqual(self.client.get('/automation/policy').status_code, 403)
        self.assertEqual(self.client.get('/automation/history', headers={**self.headers, 'Origin': 'https://evil.example'}).status_code, 403)
        response = self.client.get('/automation/policy', headers=self.headers)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertFalse(response.json()['enabled'])
        self.assertEqual(self.client.post('/automation/plan', headers=self.headers, json={'question': 'test'}).status_code, 403)

    def test_natural_language_plan_confirmation_and_completion(self):
        self.client.put('/automation/policy', headers=self.headers, json={'enabled': True, 'automatic_tools': [], 'approved': True})
        response = self.client.post('/automation/plan', headers=self.headers, json={'question': 'Check my workstation'})
        self.assertEqual(response.status_code, 200)
        flow = response.json()['workflow']
        self.assertEqual(flow['status'], 'planned')
        path = f"/automation/workflows/{flow['id']}"
        self.assertEqual(self.client.post(path + '/start', headers=self.headers, json={'approved': False}).status_code, 403)
        self.assertEqual(self.client.post(path + '/start', headers=self.headers, json={'approved': True}).status_code, 200)
        for _ in range(100):
            result = self.client.get(path, headers=self.headers).json()
            if result['status'] != 'running':
                break
            time.sleep(.01)
        self.assertEqual(result['report']['completed'], [1])
        self.assertEqual(self.client.post(path + '/start', headers=self.headers, json={'approved': True}).status_code, 409)

    def test_strict_api_and_sensitive_escalation(self):
        response = self.client.put('/automation/policy', headers=self.headers, json={'enabled': True, 'automatic_tools': ['open_website'], 'approved': True})
        self.assertEqual(response.status_code, 403)
        response = self.client.put('/automation/policy', headers=self.headers, json={'enabled': 'yes', 'approved': True})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
