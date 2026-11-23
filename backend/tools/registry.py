"""Predefined local tools. Model output is a proposal, never execution authority."""

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import shutil
import stat
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.memory.privacy import sensitive


class ToolError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Empty(Inputs):
    pass


class FileInput(Inputs):
    root: str = Field(min_length=1, max_length=36)
    path: str = Field(default='.', min_length=1, max_length=500)


class SearchInput(FileInput):
    query: str = Field(min_length=1, max_length=100)


class AppInput(Inputs):
    application: str = Field(pattern=r'^(notepad|calculator)$')


class WebsiteInput(Inputs):
    website: str = Field(min_length=1, max_length=36)


DEFINITIONS = {
    'system_info': ('Retrieve basic OS, CPU, RAM and workspace disk information.', Empty),
    'list_directory': ('List up to 100 immediate files/folders inside an approved folder.', FileInput),
    'search_files': ('Search names, not contents, inside an approved folder; bounded recursive traversal.', SearchInput),
    'read_text': ('Read one explicitly selected UTF-8 .txt, .md, .rst or .csv file, at most 64 KiB.', FileInput),
    'open_application': ('Open an approved built-in Windows Notepad or Calculator; no arguments.', AppInput),
    'open_website': ('Open an exact approved HTTPS URL in the default browser.', WebsiteInput),
}
BLOCKED = {'.git', '.ssh', '.aws', '.azure', '.venv', 'node_modules', '__pycache__', 'appdata', 'windows', 'programdata'}


def checked_url(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in {None, 443} or parsed.query or parsed.fragment
                or any(ord(c) < 33 or ord(c) == 127 for c in value)
                or any(c in value for c in '\\"\'<>|`^') or len(value) > 1000):
            raise ValueError()
        return value
    except ValueError:
        raise ToolError('Use an exact HTTPS URL without credentials, query, fragment, or custom port.')


class ToolRegistry:
    def __init__(self, audit_path: Path):
        self.audit_path = audit_path
        self.enabled = False
        self.revision = 0
        self.roots = {}
        self.applications = []
        self.websites = {}
        self.jobs = {}
        self.events = deque(maxlen=200)
        self.lock = threading.RLock()
        self.tasks = set()

    def catalog(self):
        return [{'name': name, 'description': description, 'input_schema': schema.model_json_schema()}
                for name, (description, schema) in DEFINITIONS.items()]

    def policy(self):
        with self.lock:
            return {'enabled': self.enabled, 'roots': self.roots.copy(),
                    'applications': list(self.applications), 'websites': self.websites.copy()}

    def configure(self, enabled, directories, applications, websites):
        roots = {}
        for directory in directories:
            if len(directory) > 1000 or any(ord(char) < 32 for char in directory):
                raise ToolError('Directory path exceeds the input limit.')
            path = Path(directory)
            if not path.is_absolute() or str(directory).startswith(('\\\\', '//')):
                raise ToolError('Approve an absolute local folder, not a network share.')
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_dir() or resolved == Path(resolved.anchor) or self._reparse(path):
                    raise ToolError('Choose an existing local folder, not a drive root or link.')
                if str(resolved).startswith(('\\\\', '//')) or any(self._reparse(parent) for parent in path.parents):
                    raise ToolError('Network folders and linked ancestors are not supported.')
                if any(part.casefold() in BLOCKED for part in resolved.parts):
                    raise ToolError('System, credential, and dependency folders cannot be approved.')
            except (OSError, ValueError):
                raise ToolError('The selected directory is unavailable.')
            if str(resolved) not in roots.values():
                roots[str(uuid4())] = str(resolved)
        sites = {str(uuid4()): checked_url(url) for url in websites}
        if any(app not in {'notepad', 'calculator'} for app in applications):
            raise ToolError('Application is not in the built-in catalog.')
        with self.lock:
            self.revision += 1  # Invalidates outstanding workflow permission snapshots.
            if not enabled:
                # Revocation must still work when disk/log permissions have failed.
                self.enabled = False
            for job in self.jobs.values():
                if job['status'] in {'pending', 'running'}:
                    job['_cancel'].set()
                    job['status'] = 'cancelled'
                    try:
                        self._audit(job['tool'], 'cancelled', job['id'])
                    except ToolError:
                        pass
            self._audit('policy', 'permissions_changed')
            self.enabled = enabled
            self.roots, self.applications, self.websites = roots, list(dict.fromkeys(applications)), sites
        return self.policy()

    @staticmethod
    def _reparse(path):
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)

    def _path(self, args, file=False):
        root = self.roots.get(args['root'])
        if root is None:
            raise ToolError('Folder approval is missing or has been revoked.', 403)
        relative = args['path']
        win = PureWindowsPath(relative)
        if (win.is_absolute() or win.drive or relative.startswith(('\\', '/')) or ':' in relative
                or '\x00' in relative or any(part in {'..'} for part in win.parts)):
            raise ToolError('Use a relative path without traversal, drives, or alternate data streams.', 403)
        base = Path(root)
        path = base
        # Normalize both separators; reject links at every component, including the root.
        for part in ('.', *relative.replace('\\', '/').split('/')):
            if part in {'', '.'}:
                if self._reparse(path):
                    raise ToolError('Links and reparse points are not accessible.', 403)
                continue
            if (part.startswith('.') or part.casefold() in BLOCKED or PureWindowsPath(part).is_reserved()
                    or part.endswith((' ', '.'))):
                raise ToolError('Hidden, credential, and dependency paths are blocked.', 403)
            path = path / part
            if self._reparse(path):
                raise ToolError('Links and reparse points are not accessible.', 403)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(base) or (not file and not resolved.is_dir()):
            raise ToolError('Path is not an accessible approved directory.', 403)
        if file and (not resolved.is_file() or resolved.suffix.lower() not in {'.txt', '.md', '.rst', '.csv'}):
            raise ToolError('Select an existing UTF-8 .txt, .md, .rst or .csv document.')
        return resolved

    def validate(self, name, arguments):
        if not self.enabled:
            raise ToolError('Computer tools are disabled. Approve session permissions first.', 403)
        if name not in DEFINITIONS:
            raise ToolError('Unknown tool.', 422)
        try:
            args = DEFINITIONS[name][1].model_validate(arguments).model_dump()
        except ValidationError:
            raise ToolError('Tool inputs do not match its schema.', 422)
        if name in {'list_directory', 'search_files', 'read_text'}:
            try:
                self._path(args, file=name == 'read_text')
            except (OSError, ValueError):
                raise ToolError('The selected path is missing, invalid, or inaccessible.', 404)
        if name == 'open_application' and args['application'] not in self.applications:
            raise ToolError('This application has not been approved.', 403)
        if name == 'open_website' and args['website'] not in self.websites:
            raise ToolError('This website has not been approved.', 403)
        return args

    def propose(self, name, arguments):
        with self.lock:
            try:
                args = self.validate(name, arguments)
            except (ToolError, OSError):
                self._audit(name if name in DEFINITIONS else 'unknown', 'rejected')
                raise
            if len(self.jobs) >= 200:
                finished = [key for key, job in self.jobs.items() if job['status'] not in {'pending', 'running'}]
                for key in finished:
                    self.jobs.pop(key)
                if len(self.jobs) >= 200:
                    raise ToolError('Too many pending actions; cancel an action first.', 429)
            job = {'id': str(uuid4()), 'tool': name, 'arguments': args, 'status': 'pending',
                   'result': None, 'error': None, '_cancel': threading.Event(), '_created': time.monotonic()}
            self._audit(name, 'proposed', job['id'])
            self.jobs[job['id']] = job
            return self.view(job['id'])

    def view(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ToolError('Action not found.', 404)
            return {key: value for key, value in self.jobs[job_id].items() if not key.startswith('_')}

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise ToolError('Action not found.', 404)
            if job['status'] in {'pending', 'running'}:
                job['_cancel'].set()
                job['status'] = 'cancelled'
                try:
                    self._audit(job['tool'], 'cancelled', job_id)
                except ToolError:
                    job['error'] = 'Cancelled; audit storage is unavailable.'
            return self.view(job_id)

    async def execute(self, job_id, expected_revision=None):
        with self.lock:
            if expected_revision is not None and expected_revision != self.revision:
                raise ToolError('Tool permissions changed; generate a new workflow plan.', 409)
            job = self.jobs.get(job_id)
            if job is None:
                raise ToolError('Action not found.', 404)
            if job['status'] != 'pending':
                raise ToolError('This action is no longer pending.', 409)
            if time.monotonic() - job['_created'] > 300:
                job['status'] = 'expired'
                self._audit(job['tool'], 'expired', job_id)
                raise ToolError('Approval expired; propose the action again.', 409)
            self.validate(job['tool'], job['arguments'])
            if any(not task.done() for task in self.tasks):
                raise ToolError('Another tool is running. Cancel it or wait.', 429)
            self._audit(job['tool'], 'running', job_id)  # fail closed before any OS action
            job['status'] = 'running'
            task = asyncio.create_task(asyncio.to_thread(self._run, job))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return self.view(job_id)

    def _audit(self, name, status, job_id=None):
        event = {'id': str(uuid4()), 'operation_id': job_id, 'tool': name, 'status': status,
                 'time': datetime.now(timezone.utc).isoformat()}
        # Only operational metadata: no paths, URLs, prompts, file names, document text or results.
        self.events.appendleft(event)
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event) + '\n')
        except OSError:
            raise ToolError('Audit log is unavailable; no new tool may execute until it is writable.', 503)

    @staticmethod
    def _check(cancel, deadline):
        if cancel.is_set():
            raise ToolError('Operation cancelled.')
        if time.monotonic() > deadline:
            raise ToolError('Operation exceeded the 10-second tool limit.')

    def _run(self, job):
        try:
            result = self._perform(job['tool'], job['arguments'], job['_cancel'])
            with self.lock:
                if job['_cancel'].is_set():
                    return
                self._audit(job['tool'], 'completed', job['id'])
                job['status'], job['result'] = 'completed', result
        except Exception as exc:
            with self.lock:
                if job['_cancel'].is_set():
                    return
                job['status'] = 'failed'
                job['error'] = str(exc) if isinstance(exc, ToolError) else 'Local action failed; check access permissions and availability.'
                try:
                    self._audit(job['tool'], 'failed', job['id'])
                except ToolError:
                    job['error'] = 'Audit log is unavailable; further actions are blocked until it is writable.'

    def _perform(self, name, args, cancel):
        deadline = time.monotonic() + 10
        self._check(cancel, deadline)
        if name == 'system_info':
            disk = shutil.disk_usage(Path.cwd())
            ram = None
            if os.name == 'nt':
                import ctypes
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                                *[(key, ctypes.c_ulonglong) for key in ['total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended']]]
                memory = MemoryStatus()
                memory.length = ctypes.sizeof(memory)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                    ram = memory.total
            return {'os': platform.platform(), 'cpu': platform.processor() or 'unknown',
                    'logical_cpus': os.cpu_count(), 'total_ram_bytes': ram,
                    'workspace_disk_total_bytes': disk.total, 'workspace_disk_free_bytes': disk.free}
        if name in {'open_application', 'open_website'}:
            # Permission revocation and the final side-effect check are serialized.
            with self.lock:
                self._check(cancel, deadline)
                self.validate(name, args)
                if os.name != 'nt':
                    raise ToolError('Application and website opening currently require Windows.')
                if name == 'open_application':
                    import ctypes
                    buffer = ctypes.create_unicode_buffer(32768)
                    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
                        raise ToolError('Windows system directory is unavailable.')
                    executable = Path(buffer.value) / {'notepad': 'notepad.exe', 'calculator': 'calc.exe'}[args['application']]
                    subprocess.Popen([str(executable)], shell=False, close_fds=True)
                else:
                    os.startfile(checked_url(self.websites[args['website']]))
            return {'message': 'Open request accepted by Windows. Window or page loading is not verified.'}
        with self.lock:
            self.validate(name, args)
            path = self._path(args, file=name == 'read_text')
            base = Path(self.roots[args['root']])
        if name == 'read_text':
            with path.open('rb') as stream:
                self._verify_handle(stream, base)
                if os.fstat(stream.fileno()).st_nlink != 1:
                    raise ToolError('Hard-linked documents are blocked.', 403)
                data = stream.read(65537)
            self._check(cancel, deadline)
            if len(data) > 65536:
                raise ToolError('Document exceeds the 64 KiB reading limit.')
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise ToolError('Document is not UTF-8 text.')
            if '\x00' in text or sensitive(text):
                raise ToolError('Document contains binary or potentially sensitive data; reading was refused.')
            return {'text': text, 'untrusted_document': True, 'characters': len(text)}
        results, pending, scanned = [], [path], 0
        while pending:
            self._check(cancel, deadline)
            current = pending.pop()
            # Validate each directory afresh; never follow linked directories.
            relative = str(current.relative_to(base))
            self._path({'root': args['root'], 'path': relative})
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        self._check(cancel, deadline)
                        scanned += 1
                        if scanned > 5000:
                            return {'entries': results, 'truncated': True, 'scanned': 5000}
                        candidate = Path(entry.path)
                        if entry.name.startswith('.') or entry.name.casefold() in BLOCKED or self._reparse(candidate):
                            continue
                        rel = str(candidate.relative_to(base))
                        try:
                            self._path({'root': args['root'], 'path': rel}, file=not entry.is_dir(follow_symlinks=False))
                        except ToolError:
                            # Listings can show non-text files, but never follow their links.
                            if not candidate.resolve().is_relative_to(base):
                                continue
                        is_dir = entry.is_dir(follow_symlinks=False)
                        if name == 'list_directory' or args['query'].casefold() in entry.name.casefold():
                            results.append({'path': rel, 'kind': 'directory' if is_dir else 'file'})
                            if len(results) >= 100:
                                return {'entries': results, 'truncated': True, 'scanned': scanned}
                        if name == 'search_files' and is_dir:
                            pending.append(candidate)
            except PermissionError:
                continue
            if name == 'list_directory':
                break
        return {'entries': results, 'truncated': False, 'scanned': scanned}

    @staticmethod
    def _verify_handle(stream, base):
        # Check the actual opened file, closing the resolve/open substitution window.
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            get_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
            get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            get_path.restype = wintypes.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            size = get_path(msvcrt.get_osfhandle(stream.fileno()), buffer, len(buffer), 0)
            if not size or size >= len(buffer):
                raise ToolError('Cannot verify the selected document handle.', 403)
            actual = Path(buffer.value.removeprefix('\\\\?\\'))
        elif Path('/proc/self/fd').exists():
            actual = Path(os.readlink(f'/proc/self/fd/{stream.fileno()}'))
        else:
            raise ToolError('Secure document handle verification is unavailable.', 403)
        if not actual.is_relative_to(base):
            raise ToolError('Opened document is outside the approved folder.', 403)

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                if job['status'] in {'pending', 'running'}:
                    job['_cancel'].set()
