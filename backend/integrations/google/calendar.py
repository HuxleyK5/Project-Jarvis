"""Primary-calendar events only; event insertion is called only after exact approval."""

from datetime import datetime, timedelta, timezone


class CalendarIntegration:
    def __init__(self, api):
        self.api = api

    async def upcoming(self):
        now = datetime.now(timezone.utc)
        params = {'timeMin': now.isoformat(), 'timeMax': (now + timedelta(days=30)).isoformat(),
                  'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': 50,
                  'fields': 'items(id,summary,start,end,status,description),nextPageToken'}
        data = await self.api.request('calendar', 'GET', 'calendars/primary/events', params)
        return {'events': data.get('items', []), 'has_more': bool(data.get('nextPageToken')), 'window_days': 30, 'limit': 50}

    async def create(self, event, proposal_id):
        # Stable client-generated ID makes an uncertain create safe to inspect by ID.
        return await self.api.request('calendar', 'POST', 'calendars/primary/events', body={
            'id': proposal_id.replace('-', ''), 'summary': event['title'], 'description': event['description'],
            'start': {'dateTime': event['start']}, 'end': {'dateTime': event['end']}})
