'''HTTP Transport and retry logic.'''

import logging
import random
import secrets
import time
from typing import Any, Dict, Optional, Sequence, Tuple, Union
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..constants import (
    DEFAULT_POOL_SIZE,
    RETRYABLE_SERVER_ERRORS,
    SDK_VERSION_HEADER,
    SERVER_API_VERSION,
)
from ..exceptions import (
    IntentBusAuthError,
    IntentBusError,
    IntentBusLeaseLostError,
    IntentBusNetworkError,
    IntentBusRateLimitError,
)
from .auth import canonical_body, generate_signature

logger = logging.getLogger(__name__)

LEASE_LOSS_ENDPOINT_PREFIXES = (
    '/fulfill/',
    '/fail/',
    '/extend_claim/',
)


class IntentTransport:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        user_agent: str,
        timeout: float,
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.user_agent = user_agent
        self.timeout = timeout
        self.server_version = None
        self._warned_protocol_mismatch = False

        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=DEFAULT_POOL_SIZE,
            pool_maxsize=DEFAULT_POOL_SIZE,
            max_retries=Retry(total=0),
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def close(self):
        self.session.close()

    def _build_path(
        self,
        endpoint: str,
        params: Optional[
            Union[Dict[str, Any], Sequence[Tuple[str, Any]]]
        ],
    ) -> str:
        if not params:
            return endpoint

        filtered = [
            (k, v)
            for k, v in (
                params.items() if isinstance(params, dict) else params
            )
            if v is not None
        ]

        if not filtered:
            return endpoint

        encoded_parts = [
            f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
            for k, v in sorted(filtered, key=lambda item: item[0])
        ]
        return f"{endpoint}?{'&'.join(encoded_parts)}"

    def _parse_error(self, res: requests.Response) -> str:
        try:
            payload = res.json()
            if isinstance(payload, dict) and 'error' in payload:
                code = payload['error'].get('code', 'error')
                msg = payload['error'].get('message', '')
                return f"{code}: {msg}".strip()
        except ValueError:
            pass

        return (res.text or '').strip() or f'HTTP {res.status_code}'

    def _is_lease_loss_endpoint(self, endpoint: str) -> bool:
        return any(
            endpoint.startswith(prefix)
            for prefix in LEASE_LOSS_ENDPOINT_PREFIXES
        )

    def _handle_response(
        self,
        res: requests.Response,
        endpoint: str,
    ) -> requests.Response:
        self.server_version = res.headers.get(SDK_VERSION_HEADER)

        if self.server_version and not self._warned_protocol_mismatch:
            if (
                self.server_version.split('.')[0]
                != SERVER_API_VERSION.split('.')[0]
            ):
                logger.warning(
                    'Protocol Mismatch: Server(%s) vs Client(%s)',
                    self.server_version,
                    SERVER_API_VERSION,
                )
                self._warned_protocol_mismatch = True

        if res.status_code in (401, 403):
            raise IntentBusAuthError(self._parse_error(res))

        if res.status_code == 404:
            if self._is_lease_loss_endpoint(endpoint):
                raise IntentBusLeaseLostError(self._parse_error(res))
            raise IntentBusError(self._parse_error(res))

        if res.status_code == 429:
            raise IntentBusRateLimitError(self._parse_error(res))

        if res.status_code >= 400:
            raise IntentBusError(self._parse_error(res))

        return res

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[
            Union[Dict[str, Any], Sequence[Tuple[str, Any]]]
        ] = None,
        json_data: Optional[Any] = None,
        retries: int = 0,
        idempotency_key: Optional[str] = None,
        retry_on_server_error: bool = False,
        headers_override: Optional[Dict[str, str]] = None,
    ) -> requests.Response:

        path = self._build_path(endpoint, params)
        url = f'{self.base_url}{path}'
        body_bytes = canonical_body(json_data)

        for attempt in range(retries + 1):
            ts = str(int(time.time()))
            nonce = secrets.token_hex(16)
            sig = generate_signature(
                self.api_key,
                method,
                path,
                ts,
                nonce,
                body_bytes,
            )

            headers = {
                'X-API-KEY': self.api_key,
                'X-Timestamp': ts,
                'X-Nonce': nonce,
                'X-Signature': sig,
                'Content-Type': 'application/json',
                'User-Agent': self.user_agent,
                SDK_VERSION_HEADER: SERVER_API_VERSION,
            }

            if idempotency_key:
                headers['Idempotency-Key'] = idempotency_key

            if headers_override:
                headers.update(headers_override)

            try:
                payload_data = body_bytes if body_bytes else None
                res = self.session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    data=payload_data,
                    timeout=self.timeout,
                )

                if res.status_code == 204:
                    return res

                if (
                    retry_on_server_error
                    and res.status_code in RETRYABLE_SERVER_ERRORS
                ):
                    if attempt < retries:
                        retry_after = res.headers.get('Retry-After')
                        if retry_after:
                            try:
                                time.sleep(float(retry_after))
                            except (ValueError, TypeError):
                                time.sleep(
                                    random.uniform(
                                        0,
                                        min(60, 2 ** (attempt + 1)),
                                    )
                                )
                        else:
                            time.sleep(
                                random.uniform(
                                    0,
                                    min(60, 2 ** (attempt + 1)),
                                )
                            )
                        continue

                return self._handle_response(res, endpoint)

            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt >= retries:
                    raise IntentBusNetworkError(
                        f'Network failure ({type(e).__name__}): {e}'
                    ) from e

                time.sleep(
                    random.uniform(0, min(60, 2 ** (attempt + 1)))
                )

            except requests.RequestException as e:
                raise IntentBusError(
                    f'Unexpected transport error: {e}'
                ) from e

        raise IntentBusError('Request failed after max retries.')
