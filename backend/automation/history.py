"""Append-only metadata history; never persists workflow requests, arguments or results."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.tools.registry import DEFINITIONS, ToolError


class ExecutionHistory:
    def __init__(self, path: Path):
        self.path = path

    def append(self, workflow, status):
        record = {'workflow_id': workflow['id'], 'time': datetime.now(timezone.utc).isoformat(),
                  'status': status, 'completed': sum(step['status'] == 'completed' for step in workflow['steps']),
                  'total': len(workflow['steps']),
                  'tools': [step['tool'] if step['tool'] in DEFINITIONS else 'blocked_tool' for step in workflow['steps']]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record) + '\n')
        except OSError:
            raise ToolError('Workflow history is unavailable. New workflows cannot execute until it is writable.', 503)

    def list(self):
        if not self.path.exists():
            return []
        records = deque(maxlen=100)
        try:
            with self.path.open(encoding='utf-8') as stream:
                # Bounded line buffers; history records have no user-controlled free text.
                while line := stream.readline(8192):
                    if len(line) >= 8192:
                        raise ToolError('Workflow history contains an invalid record.', 503)
                    try:
                        item = json.loads(line)
                        if set(item) == {'workflow_id', 'time', 'status', 'completed', 'total', 'tools'}:
                            records.append(item)
                    except (ValueError, TypeError):
                        continue
        except OSError:
            raise ToolError('Workflow history is unavailable.', 503)
        return list(reversed(records))
