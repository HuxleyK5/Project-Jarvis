"""Bounded official REST requests. No arbitrary URL, redirects or automatic write retries."""

import json
import httpx

from backend.integrations.google.common import GoogleError

BASES = {'calendar': 'https://www.googleapis.com/calendar/v3/',
         'gmail': 'https://gmail.googleapis.com/gmail/v1/users/me/',
         'classroom': 'https://classroom.googleapis.com/v1/'}


class GoogleAPI:
    def __init__(self, auth):
        self.auth = auth

    async def request(self, service, method, path, params=None, body=None):
        config = self.auth.require(service)
        self.auth.verified[service] = False
        revision = config['revision']
        token = await self.auth.access_token(service)
        if self.auth.require(service)['revision'] != revision:
            raise GoogleError('Integration permissions changed. Retry after reviewing them.', 409)
        if path.startswith('/') or '..' in path or '://' in path:
            raise GoogleError('Invalid Google API resource path.', 400)
        try:
            async with self.auth.http.stream(method, BASES[service] + path, params=params, json=body,
                    headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}) as response:
                if response.status_code == 401:
                    self.auth.errors[service] = 'reauth_required'
                    raise GoogleError('Google authentication expired or was revoked. Reconnect.', 401)
                if response.status_code == 403:
                    raise GoogleError('Google denied API access. Check granted scopes, enabled API, account role, verification and Workspace administrator restrictions.', 403)
                if response.status_code == 429:
                    raise GoogleError('Google API quota or rate limit reached. Try later; no automatic retry was made.', 429)
                if not response.is_success:
                    raise GoogleError('Google API request failed. Inspect the service directly before retrying a write.', 502)
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise GoogleError('Google response exceeded the local safety limit. Narrow the request.', 502)
            if self.auth.require(service)['revision'] != revision:
                raise GoogleError('Integration was disabled or changed while the request was running; returned data was discarded.', 409)
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError()
            self.auth.verified[service] = True
            return result
        except httpx.HTTPError:
            raise GoogleError('Google could not be reached. A write may have succeeded; inspect the service before retrying.', 503)
        except (ValueError, UnicodeError):
            raise GoogleError('Google returned an invalid response. Inspect the service before retrying a write.', 502)
