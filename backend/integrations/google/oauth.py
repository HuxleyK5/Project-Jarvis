"""Desktop OAuth/PKCE with an ephemeral loopback listener and DPAPI token storage."""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from backend.integrations.google.common import SERVICES, GoogleError, scopes_for

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'


class GoogleAuth:
    def __init__(self, store, client=None):
        self.store = store
        self.http = client if client is not None else httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
        self.settings = {name: {'enabled': False, 'write': False, 'send': False, 'role': 'student', 'revision': 0} for name in SERVICES}
        self.errors = {}
        self.verified = {name: False for name in SERVICES}
        self.pending = {}
        self.locks = {name: asyncio.Lock() for name in SERVICES}

    def require(self, service):
        if service not in self.settings:
            raise GoogleError('Unknown Google integration.', 404)
        if not self.settings[service]['enabled']:
            raise GoogleError('This Google integration is disabled.', 403)
        return self.settings[service]

    def scopes(self, service):
        config = self.settings[service]
        return scopes_for(service, config['write'], config['send'], config['role'])

    def status(self):
        items = []
        for service, config in self.settings.items():
            state = 'disabled'
            try:
                setup = self.store.has('client')
                saved = self.store.has(service)
                if config['enabled']:
                    token = self.store.load(service) if saved else None
                    if not setup:
                        state = 'setup_required'
                    elif service in self.pending:
                        state = 'authorizing'
                    elif self.errors.get(service):
                        state = self.errors[service]
                    elif token is None:
                        state = 'not_connected'
                    elif token.get('client_id') != self.store.load('client').get('client_id'):
                        state = 'reauth_required'
                    elif not set(self.scopes(service)).issubset(token.get('scopes', [])):
                        state = 'permissions_missing'
                    elif token.get('expires_at', 0) <= time.time() + 60:
                        state = 'refresh_pending'
                    else:
                        state = 'connected'
            except GoogleError:
                setup, saved, state = False, False, 'secure_storage_error'
            items.append({'service': service, **{key: value for key, value in config.items() if key != 'revision'},
                          'status': state, 'client_configured': setup, 'saved_authorization': saved,
                          'requested_scopes': self.scopes(service),
                          'connection_verified': config['enabled'] and self.verified[service]})
        return items

    async def configure(self, service, enabled, write, send, role, approved):
        if service not in self.settings:
            raise GoogleError('Unknown Google integration.', 404)
        if not approved:
            raise GoogleError('Approve this integration and its requested capabilities first.', 403)
        if service == 'classroom' and (write or send) or service == 'calendar' and send:
            raise GoogleError('Requested capability is not supported for this integration.', 422)
        await self.cancel_auth(service)
        current = self.settings[service]
        self.settings[service] = {'enabled': enabled, 'write': write if enabled else False,
                                  'send': send if enabled else False, 'role': role, 'revision': current['revision'] + 1}
        self.errors.pop(service, None)
        self.verified[service] = False
        return self.status()

    async def _token_request(self, fields):
        try:
            response = await self.http.post(TOKEN_URL, data=fields)
        except httpx.HTTPError:
            raise GoogleError('Google authentication could not be reached. Check connectivity and try reconnecting.', 503)
        if response.status_code == 429:
            raise GoogleError('Google authentication is rate limited. Try again later.', 429)
        if response.status_code >= 500:
            raise GoogleError('Google authentication is temporarily unavailable. Try again later.', 503)
        if not response.is_success:
            raise GoogleError('Google authorization expired, was denied, or is unavailable. Reconnect and check OAuth/admin access.', 401)
        try:
            data = response.json()
            if (not isinstance(data.get('access_token'), str) or not data['access_token']
                    or data.get('token_type', 'Bearer').casefold() != 'bearer'
                    or not 0 < int(data.get('expires_in', 0)) <= 86400):
                raise ValueError()
            return data
        except (ValueError, TypeError, AttributeError):
            raise GoogleError('Google returned an invalid token response. Reconnect.', 502)

    async def begin(self, service):
        config = self.require(service)
        client = self.store.load('client')
        if client is None:
            raise GoogleError('Import your own Google Desktop OAuth client using the documented offline setup command.', 503)
        await self.cancel_auth(service)
        config['revision'] += 1  # A new account consent invalidates pre-existing write proposals.
        self.verified[service] = False
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        flow = {'state': secrets.token_urlsafe(32), 'verifier': verifier, 'revision': config['revision'],
                'used': False, 'scopes': self.scopes(service), 'client': client}
        server = await asyncio.start_server(lambda reader, writer: self._callback(service, flow, reader, writer), '127.0.0.1', 0, limit=16384)
        flow['server'] = server
        flow['redirect'] = f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}/'
        self.pending[service] = flow
        flow['expiry'] = asyncio.create_task(self._expire(service, flow))
        url = AUTH_URL + '?' + urlencode({'client_id': client['client_id'], 'redirect_uri': flow['redirect'],
            'response_type': 'code', 'scope': ' '.join(flow['scopes']), 'state': flow['state'],
            'code_challenge': challenge, 'code_challenge_method': 'S256', 'access_type': 'offline', 'prompt': 'consent'})
        return {'authorization_url': url, 'scopes': flow['scopes'], 'expires_in': 300}

    async def _expire(self, service, flow):
        try:
            await asyncio.sleep(300)
            if self.pending.get(service) is flow:
                await self.cancel_auth(service)
                self.errors[service] = 'authorization_timeout'
        except asyncio.CancelledError:
            pass

    async def _callback(self, service, flow, reader, writer):
        success = False
        accepted = False
        try:
            raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
            lines = raw.decode('ascii').split('\r\n')
            method, target, _ = lines[0].split(' ')
            headers = dict(line.split(':', 1) for line in lines[1:] if ':' in line)
            host = next((value.strip() for key, value in headers.items() if key.casefold() == 'host'), '')
            parsed = urlsplit(target)
            query = parse_qs(parsed.query)
            if (method != 'GET' or parsed.path != '/' or host != urlsplit(flow['redirect']).netloc
                    or flow['used'] or self.pending.get(service) is not flow
                    or not secrets.compare_digest(query.get('state', [''])[0], flow['state'])):
                raise ValueError()
            flow['used'] = True
            accepted = True
            if 'error' in query or len(query.get('code', [])) != 1:
                raise GoogleError('Google consent was denied.', 401)
            await self.finish(service, flow, query['code'][0])
            success = True
        except (Exception, asyncio.CancelledError):
            if accepted and self.settings[service]['enabled']:
                self.errors[service] = 'reauth_required'
        finally:
            if accepted and self.pending.get(service) is flow:
                await self.cancel_auth(service)
            text = 'Google authorization completed. Close this tab and return to JARVIS.' if success else 'Google authorization was not completed. Return to JARVIS and reconnect.'
            body = ('<!doctype html><title>JARVIS Google authorization</title><p>' + text + '</p>').encode()
            try:
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src \'none\'\r\nConnection: close\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                await writer.drain()
            except (ConnectionError, OSError):
                pass
            writer.close()
            await writer.wait_closed()

    async def finish(self, service, flow, code):
        data = await self._token_request({'grant_type': 'authorization_code', 'code': code,
            'client_id': flow['client']['client_id'], 'client_secret': flow['client']['client_secret'],
            'redirect_uri': flow['redirect'], 'code_verifier': flow['verifier']})
        config = self.require(service)
        if config['revision'] != flow['revision'] or self.pending.get(service) is not flow:
            raise GoogleError('Integration permissions changed during authorization. Reconnect.', 409)
        granted = data.get('scope', '').split()
        if not set(flow['scopes']).issubset(granted):
            raise GoogleError('Google did not grant all requested permissions. Review consent and reconnect.', 403)
        self.store.save(service, {'access_token': data['access_token'], 'refresh_token': data.get('refresh_token'),
            'expires_at': time.time() + int(data['expires_in']), 'scopes': granted, 'client_id': flow['client']['client_id']})
        self.errors.pop(service, None)

    async def access_token(self, service):
        self.require(service)
        if self.errors.get(service) == 'reauth_required':
            raise GoogleError('Google authentication needs renewal. Reconnect this integration.', 401)
        async with self.locks[service]:
            config = self.require(service)
            revision = config['revision']
            token = self.store.load(service)
            if not token:
                raise GoogleError('Connect this integration through Google OAuth first.', 401)
            client = self.store.load('client')
            if not client or token.get('client_id') != client['client_id']:
                raise GoogleError('OAuth client configuration changed. Reconnect this integration.', 401)
            if not set(self.scopes(service)).issubset(token.get('scopes', [])):
                raise GoogleError('The saved authorization lacks the requested permissions. Reconnect.', 403)
            if token.get('expires_at', 0) > time.time() + 60:
                return token['access_token']
            if not client or not token.get('refresh_token'):
                self.errors[service] = 'reauth_required'
                raise GoogleError('Google authorization expired. Reconnect this integration.', 401)
            try:
                fresh = await self._token_request({'grant_type': 'refresh_token', 'refresh_token': token['refresh_token'],
                    'client_id': client['client_id'], 'client_secret': client['client_secret']})
            except GoogleError as exc:
                if exc.status == 401:
                    self.errors[service] = 'reauth_required'
                raise
            if self.require(service)['revision'] != revision:
                raise GoogleError('Integration was changed during token renewal.', 409)
            token.update(access_token=fresh['access_token'], expires_at=time.time() + int(fresh['expires_in']))
            if fresh.get('refresh_token'):
                token['refresh_token'] = fresh['refresh_token']
            if fresh.get('scope'):
                token['scopes'] = fresh['scope'].split()
            if not set(self.scopes(service)).issubset(token['scopes']):
                raise GoogleError('Renewed authorization has insufficient permissions. Reconnect.', 403)
            self.store.save(service, token)
            return token['access_token']

    async def cancel_auth(self, service):
        flow = self.pending.pop(service, None)
        if flow:
            flow['server'].close()
            # Python 3.12 wait_closed also waits for active callback connections.
            # The callback closes its writer below; awaiting here would wait on itself.
            expiry = flow.get('expiry')
            if expiry and expiry is not asyncio.current_task():
                expiry.cancel()

    async def disconnect(self, service):
        config = self.require(service) if service in self.settings and self.settings[service]['enabled'] else self.settings.get(service)
        if config is None:
            raise GoogleError('Unknown Google integration.', 404)
        await self.configure(service, False, False, False, 'student', True)
        self.store.forget(service)
        return self.status()

    async def close(self):
        for service in list(self.pending):
            await self.cancel_auth(service)
        await self.http.aclose()
