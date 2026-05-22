'''Authentication and signature generation helpers.'''

import hashlib
import hmac
import json
import logging
import os
import stat
from typing import Any, Optional

from ..exceptions import IntentBusAuthError, IntentBusError

logger = logging.getLogger(__name__)


def resolve_api_key(api_key: Optional[str] = None) -> str:
    '''
    Resolve API key from:
    1. Explicit parameter
    2. INTENT_API_KEY environment variable
    3. ~/.apikey
    '''

    # Explicit parameter
    if api_key is not None:
        api_key = api_key.strip()

        if api_key:
            return api_key

        raise IntentBusAuthError('Provided API key is empty')

    # Environment variable
    env_key = os.environ.get('INTENT_API_KEY')

    if env_key:
        env_key = env_key.strip()

        if env_key:
            return env_key

    key_path = os.path.expanduser('~/.apikey')

    if os.path.exists(key_path):

        # Symlink protection
        if os.path.islink(key_path):
            raise IntentBusAuthError(
                f'Security Error: API key file {key_path} is a symlink.'
            )

        try:
            st = os.stat(key_path)

            # POSIX ownership validation
            #
            # Skip gracefully on platforms without os.getuid()
            if hasattr(os, 'getuid'):
                if st.st_uid != os.getuid():
                    raise IntentBusAuthError(
                        f'Security Error: API key file {key_path} '
                        'is not owned by the current user.'
                    )

            # Warn on insecure permissions
            #
            # Only meaningful on POSIX systems.
            if os.name == 'posix':
                insecure = bool(
                    st.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
                )

                if insecure:
                    logger.warning(
                        'Insecure permissions on %s. '
                        'Run: chmod 600 %s',
                        key_path,
                        key_path,
                    )

            with open(key_path, 'r', encoding='utf-8') as f:
                key = f.read().strip()

            if key:
                return key

            raise IntentBusAuthError(
                f'API key file {key_path} is empty'
            )

        except OSError as e:
            raise IntentBusAuthError(
                f'Failed to access API key file: {e}'
            ) from e

    raise IntentBusAuthError(
        'No API key found. '
        'Pass api_key, set INTENT_API_KEY env var, '
        'or create ~/.apikey'
    )


def canonical_body(payload: Any) -> bytes:
    '''
    Serialize payload into canonical JSON bytes.
    '''

    if payload is None:
        return b''

    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')

    except (TypeError, ValueError) as e:
        raise IntentBusError(
            f'Payload serialization failed: {e}'
        ) from e


def generate_signature(
    api_key: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body_bytes: bytes,
) -> str:
    '''
    Generate HMAC-SHA256 request signature.
    '''

    msg = b'\n'.join([
        method.upper().encode('utf-8'),
        path.encode('utf-8'),
        timestamp.encode('utf-8'),
        nonce.encode('utf-8'),
        body_bytes,
    ])

    return hmac.new(
        api_key.encode('utf-8'),
        msg,
        hashlib.sha256,
    ).hexdigest()
