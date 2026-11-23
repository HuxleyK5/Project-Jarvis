"""Read-only course grouping and published coursework; no roster, submission or grade writes."""

from backend.integrations.google.models import resource_id


class ClassroomIntegration:
    def __init__(self, api):
        self.api = api

    async def courses(self, page_token=None):
        params = {'pageSize': 30, 'courseStates': 'ACTIVE', 'fields': 'courses(id,name,section),nextPageToken'}
        if page_token:
            params['pageToken'] = page_token
        data = await self.api.request('classroom', 'GET', 'courses', params)
        return {'courses': data.get('courses', []), 'next_page_token': data.get('nextPageToken')}

    async def assignments(self, course_id, page_token=None):
        params = {'pageSize': 50, 'courseWorkStates': 'PUBLISHED',
                  'fields': 'courseWork(id,courseId,title,description,dueDate,dueTime,workType),nextPageToken'}
        if page_token:
            params['pageToken'] = page_token
        data = await self.api.request('classroom', 'GET', f'courses/{resource_id(course_id)}/courseWork', params)
        return {'course_id': course_id, 'assignments': data.get('courseWork', []), 'next_page_token': data.get('nextPageToken'),
                'due_time_zone': 'UTC', 'missing_due_date_means': 'No due date provided by Google'}
