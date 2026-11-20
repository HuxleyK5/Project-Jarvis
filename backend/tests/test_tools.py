"""Independent real read-only tool tests; OS launch effects are mocked, never opened."""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.core.brain import Brain
from backend.core.providers import ModelStatus
from backend.main import create_app
from backend.tools.registry import ToolRegistry, ToolError


class SelectionProvider:
    def __init__(self, answer='null', ready=True):
        self.answer, self.ready = answer, ready
        self.requests = []

    async def status(self):
        return ModelStatus(self.ready, 'ready' if self.ready else 'ollama_unavailable', 'Local service unavailable')

    async def stream(self, messages):
        self.requests.append(messages)
        yield self.answer

    async def close(self):
        pass


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'data'))
        self.base = Path(self.temp)
        self.folder = self.base / 'approved'
        self.folder.mkdir()
        (self.folder / 'notes.md').write_text('Synthetic project notes.', encoding='utf-8')
        (self.folder / 'nested').mkdir()
        (self.folder / 'nested' / 'plan.txt').write_text('A future project.', encoding='utf-8')
        (self.base / 'outside.txt').write_text('Outside approved scope.', encoding='utf-8')
        self.registry = ToolRegistry(self.base / 'audit.jsonl')
        self.registry.configure(True, [str(self.folder)], ['notepad', 'calculator'], ['https://example.org/'])
        self.root = next(iter(self.registry.roots))

    def perform(self, name, args):
        async def run():
            job = self.registry.propose(name, args)
            await self.registry.execute(job['id'])
            if self.registry.tasks:
                await asyncio.gather(*list(self.registry.tasks))
            return self.registry.view(job['id'])
        return asyncio.run(run())

    def test_system_information(self):
        job = self.perform('system_info', {})
        self.assertEqual(job['status'], 'completed')
        self.assertGreater(job['result']['workspace_disk_total_bytes'], 0)
        self.assertIn('cpu', job['result'])

    def test_list_directory(self):
        job = self.perform('list_directory', {'root': self.root})
        self.assertEqual(job['status'], 'completed')
        self.assertEqual({item['path'] for item in job['result']['entries']}, {'notes.md', 'nested'})

    def test_search_filename_recursively(self):
        job = self.perform('search_files', {'root': self.root, 'query': 'PLAN'})
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['result']['entries'][0]['path'], str(Path('nested') / 'plan.txt'))
        self.assertFalse(job['result']['truncated'])

    def test_read_selected_document_does_not_modify_it(self):
        original = (self.folder / 'notes.md').read_bytes()
        job = self.perform('read_text', {'root': self.root, 'path': 'notes.md'})
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['result']['text'], original.decode())
        self.assertTrue(job['result']['untrusted_document'])
        self.assertEqual((self.folder / 'notes.md').read_bytes(), original)

    @unittest.skipUnless(os.name == 'nt', 'Windows launch adapter')
    def test_open_approved_application_uses_fixed_executable_no_shell(self):
        for application in ['notepad', 'calculator']:
            with self.subTest(application=application), patch('backend.tools.registry.subprocess.Popen') as launch:
                job = self.perform('open_application', {'application': application})
                self.assertEqual(job['status'], 'completed')
                self.assertFalse(launch.call_args.kwargs['shell'])
                self.assertEqual(len(launch.call_args.args[0]), 1)
                self.assertIn('not verified', job['result']['message'])

    @unittest.skipUnless(os.name == 'nt', 'Windows browser adapter')
    def test_open_approved_website_exact_url(self):
        with patch('backend.tools.registry.os.startfile') as launch:
            job = self.perform('open_website', {'website': next(iter(self.registry.websites))})
            self.assertEqual(job['status'], 'completed')
            launch.assert_called_once_with('https://example.org/')

    def test_unknown_tools_and_strict_schema(self):
        for name, args in [('shell', {'command': 'echo bad'}), ('system_info', {'command': 'bad'}),
                           ('open_application', {'application': 'powershell'}),
                           ('search_files', {'root': self.root, 'query': 1}),
                           ('open_website', {'website': 'https://unapproved.org/'})]:
            with self.subTest(name=name), self.assertRaises(ToolError):
                self.registry.propose(name, args)

    def test_path_traversal_network_device_and_hidden_paths(self):
        for value in ['../outside.txt', '..\\outside.txt', 'C:\\Windows', '\\\\server\\share',
                      'notes.md:secret', '/etc', '.git/config', 'CON.txt', 'nested. /x']:
            with self.subTest(path=value), self.assertRaises((ToolError, OSError)):
                self.registry.propose('read_text', {'root': self.root, 'path': value})

    def test_unapproved_root(self):
        with self.assertRaises(ToolError):
            self.registry.propose('list_directory', {'root': str(self.base)})

    def test_hardlinks_refused(self):
        os.link(self.base / 'outside.txt', self.folder / 'linked.txt')
        job = self.perform('read_text', {'root': self.root, 'path': 'linked.txt'})
        self.assertEqual(job['status'], 'failed')
        self.assertIn('Hard-linked', job['error'])

    def test_reparse_refused(self):
        with patch.object(self.registry, '_reparse', return_value=True):
            with self.assertRaises(ToolError):
                self.registry.propose('read_text', {'root': self.root, 'path': 'notes.md'})

    def test_document_size_encoding_and_sensitive_guard(self):
        for filename, content in [('large.txt', b'x' * 65537), ('binary.txt', b'\xff\xff'),
                                  ('sensitive.txt', b'password: example123'), ('null.txt', b'hello\x00')]:
            (self.folder / filename).write_bytes(content)
            job = self.perform('read_text', {'root': self.root, 'path': filename})
            self.assertEqual(job['status'], 'failed')
            self.assertIsNone(job['result'])

    def test_listing_limit(self):
        for index in range(110):
            (self.folder / f'item{index}.txt').write_text('test')
        job = self.perform('list_directory', {'root': self.root})
        self.assertEqual(len(job['result']['entries']), 100)
        self.assertTrue(job['result']['truncated'])

    def test_no_execution_without_approval_and_replay_refused(self):
        job = self.registry.propose('system_info', {})
        self.assertEqual(job['status'], 'pending')
        self.assertIsNone(job['result'])
        self.registry.cancel(job['id'])
        with self.assertRaises(ToolError):
            asyncio.run(self.registry.execute(job['id']))

    def test_revocation_cancels_proposals(self):
        job = self.registry.propose('system_info', {})
        self.registry.configure(False, [], [], [])
        self.assertEqual(self.registry.view(job['id'])['status'], 'cancelled')
        with self.assertRaises(ToolError):
            self.registry.propose('system_info', {})

    def test_cancel_running_work(self):
        started = threading.Event()
        def work(name, args, cancel):
            started.set()
            cancel.wait(2)
            self.registry._check(cancel, time.monotonic() + 1)
            return {'should': 'not complete'}
        async def run():
            job = self.registry.propose('system_info', {})
            with patch.object(self.registry, '_perform', side_effect=work):
                await self.registry.execute(job['id'])
                await asyncio.to_thread(started.wait, 1)
                self.registry.cancel(job['id'])
                await asyncio.gather(*list(self.registry.tasks))
            return self.registry.view(job['id'])
        job = asyncio.run(run())
        self.assertEqual(job['status'], 'cancelled')
        self.assertIsNone(job['result'])

    def test_cancelled_native_worker_does_not_allow_overlap(self):
        released = threading.Event()
        def blocked(name, args, cancel):
            released.wait(2)
            return {}
        async def run():
            first = self.registry.propose('system_info', {})
            second = self.registry.propose('system_info', {})
            with patch.object(self.registry, '_perform', side_effect=blocked):
                await self.registry.execute(first['id'])
                self.registry.cancel(first['id'])
                try:
                    with self.assertRaises(ToolError):
                        await self.registry.execute(second['id'])
                finally:
                    released.set()
                    await asyncio.gather(*list(self.registry.tasks))
        asyncio.run(run())

    def test_missing_path_returns_clear_error(self):
        with self.assertRaises(ToolError) as error:
            self.registry.propose('read_text', {'root': self.root, 'path': 'missing.txt'})
        self.assertEqual(error.exception.status, 404)

    def test_expiration(self):
        job = self.registry.propose('system_info', {})
        self.registry.jobs[job['id']]['_created'] -= 301
        with self.assertRaises(ToolError):
            asyncio.run(self.registry.execute(job['id']))
        self.assertEqual(self.registry.view(job['id'])['status'], 'expired')

    def test_audit_excludes_inputs_and_outputs(self):
        self.perform('read_text', {'root': self.root, 'path': 'notes.md'})
        text = self.registry.audit_path.read_text()
        self.assertNotIn('notes.md', text)
        self.assertNotIn('Synthetic', text)
        self.assertNotIn(str(self.folder), text)
        self.assertIn('completed', text)
        self.assertTrue(all(set(json.loads(line)) == {'id', 'operation_id', 'tool', 'status', 'time'} for line in text.splitlines()))

    def test_log_failure_prevents_execution_but_allows_cancel(self):
        job = self.registry.propose('system_info', {})
        with patch.object(Path, 'open', side_effect=PermissionError()):
            with self.assertRaises(ToolError):
                asyncio.run(self.registry.execute(job['id']))
            self.registry.cancel(job['id'])
        self.assertEqual(self.registry.view(job['id'])['status'], 'cancelled')

    def test_website_validation(self):
        for url in ['http://example.org/', 'file:///C:/test', 'javascript:alert(1)',
                    'https://u:p@example.org/', 'https://example.org/?secret=x', 'https://example.org:123/']:
            with self.subTest(url=url), self.assertRaises(ToolError):
                self.registry.configure(True, [], [], [url])

    def test_brain_selects_but_does_not_execute(self):
        provider = SelectionProvider('{"tool":"system_info","arguments":{}}')
        selection = asyncio.run(Brain(Settings(), provider).select_tool('Show system information', self.registry))
        self.assertEqual(selection['tool'], 'system_info')
        self.assertEqual(self.registry.jobs, {})
        self.assertIn('input_schema', provider.requests[0][0]['content'])

    def test_brain_refuses_invalid_or_unapproved_model_output(self):
        for answer in ['not JSON', '{"tool":"shell","arguments":{}}',
                       '{"tool":"system_info","arguments":{"shell":"bad"}}', '[]']:
            with self.subTest(answer=answer), self.assertRaises(ToolError):
                asyncio.run(Brain(Settings(), SelectionProvider(answer)).select_tool('Test', self.registry))

    def test_brain_read_requires_explicit_document(self):
        provider = SelectionProvider(json.dumps({'tool': 'read_text', 'arguments': {'root': self.root, 'path': 'notes.md'}}))
        with self.assertRaises(ToolError):
            asyncio.run(Brain(Settings(), provider).select_tool('Read something', self.registry))
        result = asyncio.run(Brain(Settings(), provider).select_tool('Read notes.md', self.registry))
        self.assertEqual(result['tool'], 'read_text')


class ToolAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.registry = ToolRegistry(Path(self.temp) / 'audit.jsonl')
        self.app = create_app(Settings(), SelectionProvider('{"tool":"system_info","arguments":{}}'), tools=self.registry)
        self.client = self.enterContext(TestClient(self.app, base_url='http://127.0.0.1:8000'))
        self.headers = {'X-Jarvis-Tool-Token': self.client.get('/tools/session').json()['token']}

    def test_host_origin_and_csrf_checks(self):
        self.assertEqual(self.client.get('/tools/policy').status_code, 403)
        self.assertEqual(self.client.get('/tools/session', headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.get('/tools/session', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.client.get('/tools/session', headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.get('/tools/policy', headers=self.headers).status_code, 200)

    def test_approval_execute_cancel_and_private_responses(self):
        response = self.client.put('/tools/policy', headers=self.headers, json={'approved': False, 'enabled': True})
        self.assertEqual(response.status_code, 403)
        response = self.client.put('/tools/policy', headers=self.headers, json={'approved': True, 'enabled': True})
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/tools/proposals', headers=self.headers, json={'tool': 'system_info', 'arguments': {}})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        job = response.json()
        response = self.client.post(f"/tools/operations/{job['id']}/execute", headers=self.headers, json={'approved': False})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(f"/tools/operations/{job['id']}/execute", headers=self.headers, json={'approved': True})
        self.assertEqual(response.status_code, 200)
        for _ in range(100):
            result = self.client.get(f"/tools/operations/{job['id']}", headers=self.headers).json()
            if result['status'] != 'running':
                break
            time.sleep(.01)
        self.assertEqual(result['status'], 'completed')
        response = self.client.post(f"/tools/operations/{job['id']}/execute", headers=self.headers, json={'approved': True})
        self.assertEqual(response.status_code, 409)

    def test_ai_proposal_is_pending_not_executed(self):
        self.client.put('/tools/policy', headers=self.headers, json={'approved': True, 'enabled': True})
        response = self.client.post('/tools/plan', headers=self.headers, json={'question': 'Show my system info'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['proposal']['status'], 'pending')
        self.assertIsNone(response.json()['proposal']['result'])

    def test_settings_default_off_and_schema_available(self):
        self.assertFalse(self.client.get('/tools/policy', headers=self.headers).json()['enabled'])
        self.assertEqual(len(self.client.get('/tools/session').json()['catalog']), 6)
        self.assertEqual(self.client.post('/tools/proposals', headers=self.headers, json={'tool': 'system_info'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
