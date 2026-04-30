import hashlib
import hmac
import json
import os
import random
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

from .exceptions import IntentBusError, IntentBusAuthError, IntentBusRateLimitError


class IntentClient:
    def __init__(
        self,
        host: str = "https://dsecurity.pythonanywhere.com",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        user_agent: str = "intent-bus-sdk/1.0.2",
    ):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

        key = api_key or os.environ.get("INTENT_API_KEY")
        if not key:
            key_path = os.path.expanduser("~/.apikey")
            if os.path.exists(key_path):
                try:
                    mode = os.stat(key_path).st_mode
                    if mode & 0o077:
                        print("[IntentBus] Warning: ~/.apikey is not secure. Run 'chmod 600 ~/.apikey'")
                except OSError:
                    pass
                with open(key_path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
            else:
                raise IntentBusAuthError(
                    "No API key found. Pass it directly, set INTENT_API_KEY in env, or create a ~/.apikey file."
                )

        if not key:
            raise IntentBusAuthError("Empty API key.")

        self.api_key = key
        self.session = requests.Session()

    def _build_path(self, endpoint: str, params: Optional[Dict[str, Any]]) -> str:
        if not params:
            return endpoint

        filtered = [(k, v) for k, v in params.items() if v is not None]
        if not filtered:
            return endpoint

        # Stable ordering prevents signature drift.
        query_string = urlencode(sorted(filtered), doseq=True)
        return f"{endpoint}?{query_string}"

    def _canonical_body(self, json_data: Optional[Dict[str, Any]]) -> bytes:
        if json_data is None:
            return b""
        return json.dumps(
            json_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def _generate_signature(self, method: str, path: str, ts: str, nonce: str, body_bytes: bytes) -> str:
        msg = b"\n".join([
            method.upper().encode("utf-8"),
            path.encode("utf-8"),
            ts.encode("utf-8"),
            nonce.encode("utf-8"),
            body_bytes,
        ])
        return hmac.new(self.api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    def _error_message(self, res: requests.Response) -> str:
        try:
            payload = res.json()
        except ValueError:
            text = (res.text or "").strip()
            return text or f"HTTP {res.status_code}"

        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                code = err.get("code", "error")
                message = err.get("message", "")
                return f"{code}: {message}".strip()
        return (res.text or "").strip() or f"HTTP {res.status_code}"

    def _handle_response(self, res: requests.Response) -> requests.Response:
        if res.status_code == 401:
            raise IntentBusAuthError(self._error_message(res))
        if res.status_code == 403:
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
    ) -> requests.Response:
        path = self._build_path(endpoint, params)
        url = f"{self.host}{path}"
        body_bytes = self._canonical_body(json_data)

        last_exc: Optional[Exception] = None

        for attempt in range(retries + 1):
            # Fresh timestamp + nonce on every attempt, because the server stores nonces.
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
                return self._handle_response(res)

            except requests.RequestException as e:
                last_exc = e
                if attempt >= retries:
                    raise IntentBusError(f"Network error during {method} {endpoint}: {e}") from e
                time.sleep((2 ** attempt) + random.uniform(0.0, 0.5))

        raise IntentBusError(f"Network error during {method} {endpoint}: {last_exc}")

    def publish(self, goal: str, payload: Any, reward: int = 0, idempotency_key: Optional[str] = None):
        """
        Publish a new intent.
        Retries are enabled because the request is idempotent when the same Idempotency-Key is reused.
        """
        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)

        res = self._request(
            "POST",
            "/intent",
            json_data={"goal": goal, "payload": payload, "reward": reward},
            retries=2,
            idempotency_key=idempotency_key,
        )
        return res.json()

    def claim(self, goal: Optional[str] = None):
        """
        Claim the next available intent for a goal.
        No automatic retries: this is a state-changing poll, and replaying it can claim a different job.
        """
        params = {"goal": goal} if goal else None
        res = self._request("POST", "/claim", params=params, retries=0)
        if res.status_code == 204:
            return None
        return res.json()

    def fail(self, intent_id: str, error: str = "Worker failed"):
        """
        Mark an intent as failed.
        No automatic retries; a replay after a partial failure could change state twice.
        """
        res = self._request(
            "POST",
            f"/fail/{intent_id}",
            json_data={"error": error},
            retries=0,
        )
        return res.json()

    def fulfill(self, intent_id: str):
        """
        Mark an intent as fulfilled.
        No automatic retries; the server may have already applied the state change.
        """
        res = self._request("POST", f"/fulfill/{intent_id}", retries=0)
        return res.json()

    def set(self, key: str, value: Any, ttl: int = 600, idempotency_key: Optional[str] = None):
        """
        Store a value in the ephemeral key-value store.
        Retries are enabled because Idempotency-Key makes retries safe.
        """
        if idempotency_key is None:
            idempotency_key = secrets.token_hex(16)

        res = self._request(
            "POST",
            f"/set/{key}",
            json_data={"value": value, "ttl": ttl},
            retries=2,
            idempotency_key=idempotency_key,
        )
        return res.json()

    def get(self, key: str):
        """
        Retrieve a value from the ephemeral key-value store.
        Safe to retry.
        """
        res = self._request("GET", f"/get/{key}", retries=2)
        return res.json().get("value")

    def listen(self, goal: str, handler, poll_interval: float = 10.0):
        """
        Blocking worker loop.
        Polls for intents matching goal, calls handler(payload), then fulfills the intent.
        On handler failure, the job is explicitly failed.
        """
        print(f"[IntentBus] Listening for '{goal}'...")

        while True:
            try:
                job = self.claim(goal=goal)
                if job:
                    attempt = job.get("claim_attempts", 1)
                    print(f"[IntentBus] Claimed {job['id']} (Attempt {attempt})")
                    try:
                        handler(job["payload"])
                        self.fulfill(job["id"])
                        print(f"[IntentBus] Fulfilled {job['id']}")
                    except Exception as handler_err:
                        print(f"[IntentBus] Handler failed for {job['id']}: {handler_err}")
                        try:
                            self.fail(job["id"], str(handler_err))
                        except IntentBusError as fail_err:
                            print(f"[IntentBus] Failed to record failure for {job['id']}: {fail_err}")

            except IntentBusAuthError as e:
                print(f"[IntentBus] Auth error: {e}")
                break
            except IntentBusRateLimitError:
                print("[IntentBus] Rate limited. Backing off...")
                time.sleep(30)
            except IntentBusError as e:
                print(f"[IntentBus] Error: {e}")
            except Exception as e:
                print(f"[IntentBus] Unexpected error: {e}")

            time.sleep(poll_interval + random.uniform(0.0, 1.0))
