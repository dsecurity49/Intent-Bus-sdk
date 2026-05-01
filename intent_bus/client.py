import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import stat
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from .version import __version__
from .exceptions import IntentBusAuthError, IntentBusError, IntentBusRateLimitError

logger = logging.getLogger(__name__)

class IntentClient:
    def __init__(
        self,
        base_url: str = "https://dsecurity.pythonanywhere.com",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        user_agent: str = f"intent-bus-sdk/{__version__}",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

        key = api_key or os.environ.get("INTENT_API_KEY")
        if not key:
            key_path = os.path.expanduser("~/.apikey")
            if os.path.exists(key_path):
                try:
                    mode = os.stat(key_path).st_mode
                    if stat.S_IMODE(mode) & 0o077:
                        logger.warning(
                            "[IntentBus] ~/.apikey is not restricted. Run 'chmod 600 ~/.apikey'"
                        )
                except OSError:
                    pass

                with open(key_path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
            else:
                raise IntentBusAuthError(
                    "No API key found. Pass it directly, set INTENT_API_KEY, or create ~/.apikey"
                )

        if not key:
            raise IntentBusAuthError("Empty API key.")

        self.api_key = key

        # Connection pooling for high-throughput concurrency
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Explicitly close the underlying requests session."""
        self.session.close()

    def _build_path(self, endpoint: str, params: Optional[Dict[str, Any]]) -> str:
        if not params:
            return endpoint

        filtered = [(k, v) for k, v in params.items() if v is not None]
        if not filtered:
            return endpoint

        # RFC 3986 encoding with lexicographic key ordering for HMAC determinism
        encoded_parts = []
        for k, v in sorted(filtered, key=lambda item: item[0]):
            encoded_parts.append(
                f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
            )

        return f"{endpoint}?{'&'.join(encoded_parts)}"

    def _canonical_body(self, json_data: Optional[Dict[str, Any]]) -> bytes:
        if json_data is None:
            return b""
        try:
            return json.dumps(
                json_data,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except TypeError as e:
            raise IntentBusError(f"Payload serialization failed: {e}") from e

    def _generate_signature(
        self,
        method: str,
        path: str,
        ts: str,
        nonce: str,
        body_bytes: bytes,
    ) -> str:
        msg = b"\n".join(
            [
                method.upper().encode("utf-8"),
                path.encode("utf-8"),
                ts.encode("utf-8"),
                nonce.encode("utf-8"),
                body_bytes,
            ]
        )
        return hmac.new(
            self.api_key.encode("utf-8"),
            msg,
            hashlib.sha256,
        ).hexdigest()

    def _error_message(self, res: requests.Response) -> str:
        try:
            payload = res.json()
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict):
                    return f"{err.get('code', 'error')}: {err.get('message', '')}".strip()
        except ValueError:
            pass
        return (res.text or "").strip() or f"HTTP {res.status_code}"

    def _handle_response(self, res: requests.Response) -> requests.Response:
        if res.status_code in (401, 403):
            raise IntentBusAuthError(self._error_message(res))
        if res.status_code == 429:
            raise IntentBusRateLimitError(self._error_message(res))
        if res.status_code >= 400:
            raise IntentBusError(self._error_message(res))
        return res

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retries: int = 0,
        idempotency_key: Optional[str] = None,
        retry_on_server_error: bool = False,
    ) -> requests.Response:
        path = self._build_path(endpoint, params)
        url = f"{self.base_url}{path}"
        body_bytes = self._canonical_body(json_data)

        last_exc: Optional[Exception] = None

        for attempt in range(retries + 1):
            ts = str(int(time.time()))
            nonce = secrets.token_hex(16)
            sig = self._generate_signature(method, path, ts, nonce, body_bytes)

            headers = {
                "X-API-KEY": self.api_key,
                "X-Timestamp": ts,
                "X-Nonce": nonce,
                "X-Signature": sig,
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            }
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            try:
                res = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    data=body_bytes if body_bytes else None,
                    timeout=self.timeout,
                )

                if retry_on_server_error and res.status_code in (500, 502, 503, 504):
                    if attempt < retries:
                        time.sleep((2**attempt) + random.uniform(0.0, 0.5))
                        continue

                return self._handle_response(res)

            except requests.RequestException as e:
                last_exc = e
                if attempt >= retries:
                    raise IntentBusError(f"Network error: {e}") from e
                time.sleep((2**attempt) + random.uniform(0.0, 0.5))

        raise IntentBusError(f"Request failed: {last_exc}")

    def publish(self, goal: str, payload: Any, visibility: str = "private", idempotency_key: Optional[str] = None):
        if visibility not in ("private", "public"):
            raise IntentBusError("visibility must be 'private' or 'public'")
        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)

        res = self._request(
            "POST", "/intent",
            json_data={"goal": goal, "payload": payload, "visibility": visibility},
            retries=2,
            idempotency_key=idempotency_key,
            retry_on_server_error=True
        )
        return res.json()

    def claim(self, goal: Optional[str] = None, publisher: Optional[str] = None):
        params = {}
        if goal: params["goal"] = goal
        if publisher: params["publisher"] = publisher
        res = self._request("POST", "/claim", params=params, retries=0)
        return res.json() if res.status_code == 200 else None

    def fail(self, intent_id: str, error: str = "Worker failure"):
        res = self._request("POST", f"/fail/{intent_id}", json_data={"error": error})
        return res.json()

    def fulfill(self, intent_id: str):
        res = self._request("POST", f"/fulfill/{intent_id}")
        return res.json()

    def set(self, key: str, value: Any, ttl: int = 600, idempotency_key: Optional[str] = None):
        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)
        res = self._request(
            "POST", f"/set/{key}",
            json_data={"value": value, "ttl": ttl},
            retries=2,
            idempotency_key=idempotency_key,
            retry_on_server_error=True
        )
        return res.json()

    def get(self, key: str):
        res = self._request("GET", f"/get/{key}", retries=2, retry_on_server_error=True)
        return res.json().get("value")

    def listen(self, goal: str, handler, poll_interval: float = 5.0, publisher: Optional[str] = None):
        print(f"[IntentBus] Listening for '{goal}'...")
        try:
            while True:
                try:
                    job = self.claim(goal=goal, publisher=publisher)
                    if job:
                        print(f"[IntentBus] Claimed {job['id']}")
                        try:
                            if handler(job["payload"]) is not False:
                                self.fulfill(job["id"])
                                print(f"[IntentBus] Fulfilled {job['id']}")
                        except Exception as e:
                            print(f"[IntentBus] Handler error: {e}")
                            self.fail(job["id"], str(e))
                except IntentBusAuthError as e:
                    print(f"[IntentBus] Auth Error: {e}")
                    break
                except IntentBusRateLimitError:
                    time.sleep(30)
                except Exception as e:
                    print(f"[IntentBus] Error: {e}")
                time.sleep(poll_interval + random.uniform(0.0, 1.0))
        except KeyboardInterrupt:
            print("[IntentBus] Shutdown requested")
