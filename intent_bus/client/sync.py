'''Synchronous HTTP Client for the Intent Protocol.'''

import json
import secrets
from typing import Any, Dict, Generic, Optional, Sequence, TypeVar, Union

from ..constants import (
    DEFAULT_NAMESPACE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    RESULT_JSON,
    RESULT_TEXT,
    USER_AGENT_PREFIX,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
)
from ..exceptions import IntentBusError
from ..models.intent import ClaimedIntent, IntentResult, IntentStatus
from ..version import __version__
from .auth import resolve_api_key
from .transport import IntentTransport

T = TypeVar('T')

_OMITTED = object()


class ClaimResponse(Generic[T]):
    def __init__(
        self,
        data: Optional[T],
        status_code: int = 200,
        retry_after: Optional[float] = None,
    ):
        self.data = data
        self.status_code = status_code
        self.retry_after = retry_after

    def __bool__(self) -> bool:
        return bool(self.data is not None)

    def __getattr__(self, name):
        data = object.__getattribute__(self, 'data')

        if data is None:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute "
                f"'{name}' (data is None)"
            )

        return getattr(data, name)

    def get(self, key: str, default: Any = None) -> Any:
        if self.data is None:
            return default

        if hasattr(self.data, key):
            return getattr(self.data, key)

        return getattr(self.data, 'extra', {}).get(key, default)

    def __getitem__(self, key: str) -> Any:
        if self.data is None:
            raise KeyError(f"Cannot access '{key}' on empty claim")

        if hasattr(self.data, key):
            return getattr(self.data, key)

        extra = getattr(self.data, 'extra', {})

        if key in extra:
            return extra[key]

        raise KeyError(key)


class IntentClient:
    def __init__(
        self,
        base_url: str = 'https://dsecurity.pythonanywhere.com',
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: Optional[str] = None,
    ):
        self.api_key = resolve_api_key(api_key)

        self.user_agent = (
            user_agent or f'{USER_AGENT_PREFIX}/{__version__}'
        )

        self.transport = IntentTransport(
            base_url=base_url,
            api_key=self.api_key,
            user_agent=self.user_agent,
            timeout=timeout,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.transport.close()

    @property
    def server_version(self) -> Optional[str]:
        return self.transport.server_version

    def publish(
        self,
        goal: str,
        payload: Any,
        namespace: str = DEFAULT_NAMESPACE,
        visibility: str = VISIBILITY_PRIVATE,
        priority: int = 100,
        delay: float = 0.0,
        max_attempts: int = 3,
        backoff_base: float = 5.0,
        target_worker: Optional[str] = None,
        required_capability: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[IntentStatus]:

        if not isinstance(goal, str) or not goal.strip():
            raise IntentBusError(
                'goal must be a non-empty string'
            )

        if not isinstance(namespace, str) or not namespace.strip():
            raise IntentBusError(
                'namespace must be a non-empty string'
            )

        if visibility not in (
            VISIBILITY_PRIVATE,
            VISIBILITY_PUBLIC,
        ):
            raise IntentBusError(
                'visibility must be "private" or "public"'
            )

        if (
            not isinstance(priority, int)
            or not (0 <= priority <= 1000)
        ):
            raise IntentBusError(
                f'priority must be between 0 and 1000, got {priority}'
            )

        if (
            not isinstance(delay, (int, float))
            or delay < 0
        ):
            raise IntentBusError(
                f'delay must be non-negative, got {delay}'
            )

        if (
            not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise IntentBusError(
                f'max_attempts must be >= 1, got {max_attempts}'
            )

        if (
            not isinstance(backoff_base, (int, float))
            or backoff_base <= 0
        ):
            raise IntentBusError(
                f'backoff_base must be > 0, got {backoff_base}'
            )

        if target_worker and len(str(target_worker)) > 64:
            raise IntentBusError(
                'target_worker cannot exceed 64 characters'
            )

        if (
            required_capability
            and len(str(required_capability)) > 64
        ):
            raise IntentBusError(
                'required_capability cannot exceed 64 characters'
            )

        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)

        data = {
            'goal': goal,
            'payload': payload,
            'namespace': namespace,
            'visibility': visibility,
            'priority': priority,
            'delay': delay,
            'max_attempts': max_attempts,
            'backoff_base': backoff_base,
        }

        if target_worker:
            data['target_worker'] = target_worker

        if required_capability:
            data['required_capability'] = required_capability

        res = self.transport.request(
            'POST',
            '/intent',
            json_data=data,
            retries=DEFAULT_RETRIES,
            idempotency_key=idempotency_key,
            retry_on_server_error=True,
        )

        if res.status_code in (200, 201):
            return IntentStatus.from_dict(res.json())

        return None

    def claim(
        self,
        goal: Optional[str] = None,
        publisher: Optional[str] = None,
        namespace: str = DEFAULT_NAMESPACE,
        worker_id: Optional[str] = None,
        capabilities: Optional[
            Union[str, Sequence[str]]
        ] = None,
    ) -> ClaimResponse[ClaimedIntent]:

        params = [('namespace', namespace)]

        if goal:
            params.append(('goal', goal))

        if publisher:
            params.append(('publisher', publisher))

        headers = {}

        if worker_id:
            headers['X-Worker-ID'] = worker_id

        if capabilities:
            if isinstance(capabilities, str):
                normalized = capabilities.strip()

            else:
                cleaned = [
                    str(c).strip()
                    for c in capabilities
                    if str(c).strip()
                ]

                normalized = ','.join(cleaned)

            if normalized:
                headers['X-Worker-Capabilities'] = normalized

        res = self.transport.request(
            'POST',
            '/claim',
            params=params,
            headers_override=headers,
            retries=0,
        )

        if res.status_code == 204:
            retry_after = None

            rh = res.headers.get('Retry-After')

            if rh:
                try:
                    retry_after = float(rh.strip())

                    if retry_after < 0:
                        retry_after = None

                except (TypeError, ValueError):
                    retry_after = None

            return ClaimResponse(
                None,
                status_code=204,
                retry_after=retry_after,
            )

        if res.status_code == 200:
            raw_data = res.json()

            model = (
                ClaimedIntent.from_dict(raw_data)
                if raw_data and 'id' in raw_data
                else None
            )

            return ClaimResponse(
                model,
                status_code=200,
            )

        return ClaimResponse(
            None,
            status_code=res.status_code,
        )

    def extend_claim(
        self,
        intent_id: str,
        claim_token: str,
        seconds: int = 60,
    ) -> Optional[Dict[str, Any]]:

        if not intent_id.strip():
            raise IntentBusError('intent_id cannot be empty')

        if not claim_token.strip():
            raise IntentBusError('claim_token cannot be empty')

        if not isinstance(seconds, int) or seconds <= 0:
            raise IntentBusError(
                'seconds must be a positive integer'
            )

        res = self.transport.request(
            'POST',
            f'/extend_claim/{intent_id}',
            json_data={
                'claim_token': claim_token,
                'seconds': seconds,
            },
        )

        return (
            res.json()
            if res.status_code == 200
            else None
        )

    def fail(
        self,
        intent_id: str,
        claim_token: str,
        error: str = 'Worker failure',
    ) -> Optional[Dict[str, Any]]:

        if not intent_id.strip():
            raise IntentBusError('intent_id cannot be empty')

        if not claim_token.strip():
            raise IntentBusError('claim_token cannot be empty')

        res = self.transport.request(
            'POST',
            f'/fail/{intent_id}',
            json_data={
                'claim_token': claim_token,
                'error': error,
            },
        )

        return (
            res.json()
            if res.status_code == 200
            else None
        )

    def fulfill(
        self,
        intent_id: str,
        claim_token: str,
        result: Any = _OMITTED,
        result_type: str = RESULT_JSON,
    ) -> Optional[Dict[str, Any]]:

        if not intent_id.strip():
            raise IntentBusError('intent_id cannot be empty')

        if not claim_token.strip():
            raise IntentBusError('claim_token cannot be empty')

        if result_type not in (
            RESULT_JSON,
            RESULT_TEXT,
        ):
            raise IntentBusError(
                f'result_type must be '
                f'"{RESULT_JSON}" or "{RESULT_TEXT}"'
            )

        if (
            result is _OMITTED
            and result_type != RESULT_JSON
        ):
            raise IntentBusError(
                'Providing a result_type requires a result body'
            )

        if (
            result_type == RESULT_TEXT
            and result is not _OMITTED
            and not isinstance(result, str)
        ):
            raise IntentBusError(
                "Result payload must be a string when "
                "result_type is 'text'"
            )

        data = {
            'claim_token': claim_token,
            'result_type': result_type,
        }

        if result is not _OMITTED:
            data['result'] = result

        res = self.transport.request(
            'POST',
            f'/fulfill/{intent_id}',
            json_data=data,
        )

        return (
            res.json()
            if res.status_code == 200
            else None
        )

    def get_result(
        self,
        intent_id: str,
    ) -> Optional[IntentResult]:

        res = self.transport.request(
            'GET',
            f'/result/{intent_id}',
            retries=DEFAULT_RETRIES,
            retry_on_server_error=True,
        )

        if res.status_code == 200:
            return IntentResult.from_dict(res.json())

        return None

    def get_status(
        self,
        intent_id: str,
    ) -> Optional[IntentStatus]:

        res = self.transport.request(
            'GET',
            f'/status/{intent_id}',
            retries=DEFAULT_RETRIES,
            retry_on_server_error=True,
        )

        if res.status_code == 200:
            return IntentStatus.from_dict(res.json())

        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int = 600,
        idempotency_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        if not isinstance(ttl, int) or ttl <= 0:
            raise IntentBusError(
                'ttl must be a positive integer'
            )

        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)

        safe_value = (
            json.dumps(
                value,
                separators=(',', ':'),
                allow_nan=False,
            )
            if isinstance(value, (dict, list))
            else value
        )

        res = self.transport.request(
            'POST',
            f'/set/{key}',
            json_data={
                'value': safe_value,
                'ttl': ttl,
            },
            retries=DEFAULT_RETRIES,
            idempotency_key=idempotency_key,
            retry_on_server_error=True,
        )

        return (
            res.json()
            if res.status_code == 200
            else None
        )

    def get(self, key: str) -> Optional[Any]:

        res = self.transport.request(
            'GET',
            f'/get/{key}',
            retries=DEFAULT_RETRIES,
            retry_on_server_error=True,
        )

        if res.status_code != 200:
            return None

        val = res.json().get('value')

        if (
            isinstance(val, str)
            and (
                val.startswith('{')
                or val.startswith('[')
            )
        ):
            try:
                return json.loads(val)

            except json.JSONDecodeError:
                pass

        return val
