"""Optional APScheduler 3.x adapter; no imports/downloads until scheduling is requested."""

from importlib.util import find_spec

from backend.tools.registry import ToolError


class WorkflowScheduler:
    def __init__(self):
        self.scheduler = None

    def available(self):
        return find_spec('apscheduler') is not None

    def add(self, workflow_id, when, callback, missed):
        if not self.available():
            raise ToolError('APScheduler is not installed. With your approval, install backend/automation/requirements.txt in .venv. Immediate workflows still work.', 503)
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler(timezone='UTC')
            self.scheduler.add_listener(lambda event: missed(event.job_id), EVENT_JOB_MISSED | EVENT_JOB_ERROR)
            self.scheduler.start()
        self.scheduler.add_job(callback, 'date', run_date=when, args=[workflow_id], id=workflow_id,
                               misfire_grace_time=30, coalesce=True, max_instances=1)

    def remove(self, workflow_id):
        if self.scheduler is not None:
            from apscheduler.jobstores.base import JobLookupError
            try:
                self.scheduler.remove_job(workflow_id)
            except JobLookupError:
                pass

    def close(self):
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
