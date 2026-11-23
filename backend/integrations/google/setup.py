"""Offline CLI import of a user-provided Google Desktop OAuth client file."""

import argparse
import json
import re
from pathlib import Path

from backend.integrations.google.secure_store import SecureStore
from backend.integrations.google.common import GoogleError

DEFAULT_STORE = Path(__file__).resolve().parents[3] / 'data' / 'google'


def import_client(path, store):
    try:
        if path.stat().st_size > 16384:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8-sig'))['installed']
        client_id, secret = value['client_id'], value['client_secret']
        if (not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', client_id)
                or len(client_id) > 300 or not isinstance(secret, str) or not 1 <= len(secret) <= 500
                or any(char.isspace() for char in client_id + secret)):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise GoogleError('Choose an official Desktop app OAuth client JSON file. Web/service-account credentials are not supported.')
    # Do not trust endpoint URLs inside imported JSON; all URLs in the OAuth adapter are fixed.
    store.save('client', {'client_id': client_id, 'client_secret': secret})


def main():
    parser = argparse.ArgumentParser(description='Encrypt a Google Desktop OAuth client for the current Windows user. Stop JARVIS before changing the client.')
    parser.add_argument('--client-file', required=True, type=Path)
    args = parser.parse_args()
    try:
        import_client(args.client_file, SecureStore(DEFAULT_STORE))
    except GoogleError as exc:
        parser.exit(1, str(exc) + '\n')
    print('OAuth client encrypted locally. Start JARVIS, enable one integration, and connect through Google consent.')


if __name__ == '__main__':
    main()
