"""Authorized mailbox reads, bounded plain-text thread extraction and explicit MIME writes."""

import base64
from email.message import EmailMessage
from email import policy
from email.utils import formatdate
from uuid import uuid4

from backend.integrations.google.models import resource_id, MailInput
from backend.integrations.google.common import GoogleError


def message_view(message):
    payload = message.get('payload', {})
    headers = {item.get('name', '').lower(): item.get('value', '')[:1000] for item in payload.get('headers', [])}
    texts = []
    def visit(part, depth=0):
        if depth > 10:
            return
        if part.get('mimeType') == 'text/plain' and not part.get('filename'):
            data = part.get('body', {}).get('data', '')
            try:
                texts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace')[:12000])
            except (ValueError, TypeError):
                pass
        for child in part.get('parts', [])[:20]:
            visit(child, depth + 1)
    visit(payload)
    return {'id': message.get('id'), 'thread_id': message.get('threadId'), 'subject': headers.get('subject', '(no subject)'),
            'from': headers.get('from', ''), 'to': headers.get('to', ''), 'date': headers.get('date', ''),
            'text': '\n'.join(texts)[:12000], 'snippet': message.get('snippet', '')[:1000],
            'plain_text_available': bool(texts), 'untrusted_content': True}


def raw_mail(mail, sender):
    message = EmailMessage(policy=policy.SMTP)
    message['From'] = sender
    message['To'] = ', '.join(mail['to'])
    message['Subject'] = mail['subject']
    message['Date'] = formatdate(usegmt=True)
    message['Message-ID'] = f'<{uuid4().hex}@{sender.split("@")[-1]}>'
    message.set_content(mail['body'])
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


class GmailIntegration:
    def __init__(self, api):
        self.api = api

    async def sender(self):
        profile = await self.api.request('gmail', 'GET', 'profile', {'fields': 'emailAddress'})
        address = profile.get('emailAddress')
        try:
            if not isinstance(address, str):
                raise ValueError()
            MailInput.recipients([address])
        except ValueError:
            raise GoogleError('Google did not return a valid authorized sender address.', 502)
        return address

    async def search(self, query='', page_token=None):
        params = {'q': query, 'maxResults': 20}
        if page_token:
            params['pageToken'] = page_token
        data = await self.api.request('gmail', 'GET', 'messages', params=params)
        # List returns IDs, not bodies; only selected messages are read.
        return {'messages': data.get('messages', []), 'next_page_token': data.get('nextPageToken')}

    async def read(self, message_id):
        data = await self.api.request('gmail', 'GET', 'messages/' + resource_id(message_id), {'format': 'full'})
        return message_view(data)

    async def thread(self, thread_id):
        data = await self.api.request('gmail', 'GET', 'threads/' + resource_id(thread_id), {'format': 'full'})
        messages = data.get('messages', [])
        return {'thread_id': data.get('id', thread_id), 'messages': [message_view(item) for item in messages[-10:]],
                'truncated': len(messages) > 10}

    async def create_draft(self, mail, sender):
        data = await self.api.request('gmail', 'POST', 'drafts', body={'message': {'raw': raw_mail(mail, sender)}})
        return {'draft_id': data.get('id'), 'message_id': data.get('message', {}).get('id')}

    async def send(self, mail, sender):
        # Send exactly the approved MIME, not a remote draft that might have been edited elsewhere.
        data = await self.api.request('gmail', 'POST', 'messages/send', body={'raw': raw_mail(mail, sender)})
        return {'message_id': data.get('id'), 'thread_id': data.get('threadId')}
