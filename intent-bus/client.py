import time
import requests
from .exceptions import IntentBusError, IntentBusAuthError, IntentBusRateLimitError


class IntentClient:
    def __init__(self, host, api_key, timeout=10):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def _handle_response(self, res):
        if res.status_code == 401:
            raise IntentBusAuthError("Invalid or missing API key.")
        if res.status_code == 429:
            raise IntentBusRateLimitError("Rate limit exceeded.")
        if res.status_code >= 400:
            raise IntentBusError(f"Request failed: {res.status_code} {res.text}")
        return res

    def publish(self, goal, payload, reward=0):
        """POST a new intent onto the bus."""
        res = requests.post(
            f"{self.host}/intent",
            json={"goal": goal, "payload": payload, "reward": reward},
            headers=self.headers,
            timeout=self.timeout
        )
        self._handle_response(res)
        return res.json()

    def claim(self, goal=None):
        """Claim the next available intent. Returns None if queue is empty."""
        url = f"{self.host}/claim"
        if goal:
            url += f"?goal={goal}"
        res = requests.post(url, headers=self.headers, timeout=self.timeout)
        if res.status_code == 204:
            return None
        self._handle_response(res)
        return res.json()

    def fulfill(self, intent_id):
        """Mark an intent as fulfilled."""
        res = requests.post(
            f"{self.host}/fulfill/{intent_id}",
            headers=self.headers,
            timeout=self.timeout
        )
        self._handle_response(res)
        return res.json()

    def set(self, key, value, ttl=600):
        """Store a value in the ephemeral key-value store."""
        res = requests.post(
            f"{self.host}/set/{key}",
            json={"value": value, "ttl": ttl},
            headers=self.headers,
            timeout=self.timeout
        )
        self._handle_response(res)
        return res.json()

    def get(self, key):
        """Retrieve a value from the ephemeral key-value store."""
        res = requests.get(
            f"{self.host}/get/{key}",
            headers=self.headers,
            timeout=self.timeout
        )
        self._handle_response(res)
        return res.json().get("value")

    def listen(self, goal, handler, poll_interval=10):
        """
        Blocking worker loop. Polls for intents matching goal,
        calls handler(payload), then fulfills the intent.
        """
        print(f"[IntentBus] Listening for '{goal}'...")
        while True:
            try:
                job = self.claim(goal=goal)
                if job:
                    print(f"[IntentBus] Claimed {job['id']}")
                    handler(job["payload"])
                    self.fulfill(job["id"])
                    print(f"[IntentBus] Fulfilled {job['id']}")
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
            time.sleep(poll_interval)
