"""Integration registry and immutable, single-use external-write proposals."""

from copy import deepcopy
import time
from uuid import uuid4

from backend.integrations.google.calendar import CalendarIntegration
from backend.integrations.google.classroom import ClassroomIntegration
from backend.integrations.google.common import GoogleError
from backend.integrations.google.gmail import GmailIntegration
from backend.integrations.google.models import EventInput, MailInput
from backend.integrations.google.oauth import GoogleAuth
from backend.integrations.google.transport import GoogleAPI


class GoogleIntegrations:
    def __init__(self, store, client=None):
        self.auth = GoogleAuth(store, client)
        self.api = GoogleAPI(self.auth)
        self.adapters = {'calendar': CalendarIntegration(self.api), 'gmail': GmailIntegration(self.api),
                         'classroom': ClassroomIntegration(self.api)}
        self.proposals = {}

    def capability(self, service, action):
        config = self.auth.require(service)
        if (service == 'calendar' and action == 'create_event' and config['write']
                or service == 'gmail' and action == 'create_draft' and config['write']
                or service == 'gmail' and action == 'send_message' and config['send']):
            return config
        raise GoogleError('Enable and authorize this specific write capability before proposing an action.', 403)

    async def propose(self, service, action, payload):
        config = self.capability(service, action)
        normalized = (EventInput if service == 'calendar' else MailInput).model_validate(payload).model_dump()
        sender = await self.adapters['gmail'].sender() if service == 'gmail' else None
        if self.capability(service, action)['revision'] != config['revision']:
            raise GoogleError('Google account permissions changed while preparing the proposal.', 409)
        if len(self.proposals) >= 50:
            for key in [key for key, item in self.proposals.items() if item['status'] != 'pending' and item['status'] != 'executing']:
                del self.proposals[key]
            if len(self.proposals) >= 50:
                raise GoogleError('Too many pending Google actions. Cancel one first.', 429)
        item = {'id': str(uuid4()), 'service': service, 'action': action, 'payload': normalized,
                'sender': sender,
                'status': 'pending', 'result': None, 'error': None,
                '_created': time.monotonic(), '_revision': config['revision']}
        self.proposals[item['id']] = item
        return self.view(item['id'])

    def view(self, proposal_id):
        item = self.proposals.get(proposal_id)
        if item is None:
            raise GoogleError('Google action not found.', 404)
        return deepcopy({key: value for key, value in item.items() if not key.startswith('_')})

    async def execute(self, proposal_id, approved):
        item = self.proposals.get(proposal_id)
        if item is None:
            raise GoogleError('Google action not found.', 404)
        if not approved:
            raise GoogleError('Confirm the exact recipients/content or event details before this external action.', 403)
        if item['status'] != 'pending':
            raise GoogleError('This Google action is no longer pending. Automatic replays are blocked.', 409)
        config = self.capability(item['service'], item['action'])
        if config['revision'] != item['_revision'] or time.monotonic() - item['_created'] > 300:
            item['status'] = 'expired'
            raise GoogleError('Permissions changed or approval expired. Create a new proposal.', 409)
        item['status'] = 'executing'
        try:
            adapter = self.adapters[item['service']]
            if item['action'] == 'create_event':
                raw = await adapter.create(item['payload'], item['id'])
                result = {'event_id': raw.get('id')}
            elif item['action'] == 'create_draft':
                result = await adapter.create_draft(item['payload'], item['sender'])
            else:
                result = await adapter.send(item['payload'], item['sender'])
            if not result or not next(iter(result.values()), None):
                raise GoogleError('Google did not return a result identifier. Inspect the service before retrying.', 502)
            item['status'], item['result'] = 'completed', result
        except GoogleError as exc:
            item['status'], item['error'] = 'not_completed_or_unknown', str(exc)
            raise
        except BaseException:
            item['status'], item['error'] = 'not_completed_or_unknown', 'The request ended without a confirmed outcome. Inspect Google before retrying.'
            raise
        return self.view(proposal_id)

    def cancel(self, proposal_id):
        item = self.proposals.get(proposal_id)
        if item is None:
            raise GoogleError('Google action not found.', 404)
        if item['status'] == 'executing':
            raise GoogleError('This external request has started and cannot be recalled. Inspect Google for its outcome.', 409)
        if item['status'] == 'pending':
            item['status'] = 'cancelled'
        return self.view(proposal_id)

    def invalidate(self, service):
        for item in self.proposals.values():
            if item['service'] == service and item['status'] == 'pending':
                item['status'] = 'cancelled'
                item['payload'] = {}  # Disabling/changing capabilities forgets unexecuted content.

    async def close(self):
        self.proposals.clear()
        await self.auth.close()
