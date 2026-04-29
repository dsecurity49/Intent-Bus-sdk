import time
import requests
import os
from .exceptions import IntentBusError, IntentBusAuthError, IntentBusRateLimitError

class IntentClient:
    # Set dsecurity.pythonanywhere.com as the default host for zero-friction setup
    def __init__(self, host="https://dsecurity.pythonanywhere.com", api_key=None, timeout=10):
        self.host = host.rstrip("/")
        self.timeout = timeout
        
        # Auth Waterfall: 1. Passed Arg -> 2. Env Var -> 3. Local ~/.apikey file
        key = api_key or os.environ.get("INTENT_API_KEY")
        if not key:
            key_path = os.path.expanduser("~/.apikey")
            if os.path.exists(key_path):
                # Security Check: Warn if the key file is world/group readable
                if os.stat(key_path).st_mode & 0o077:
                    print("[IntentBus] Warning: ~/.apikey is not secure. Run 'chmod 600 ~/.apikey'")
                with open(key_path, "r") as f:
                    key = f.read().strip()
            else:
                raise IntentBusAuthError(
                    "No API key found. Pass it directly, set INTENT_API_KEY in env, or create a ~/.apikey file."
                )

        self.headers = {
            "X-API-KEY": key,
            "Content-Type": "application/json"
        }

    def _request(self, method, endpoint, **kwargs):
        """Internal helper to handle retries, timeouts, and URL construction."""
        url = f"{self.host}{endpoint}"
        for attempt in range(3):
            try:
                res = requests.request(
                    method, 
                    url, 
                    headers=self.headers, 
                    timeout=self.timeout, 
                    **kwargs
                )
                return self._handle_response(res)
            except requests.RequestException as e:
                if attempt == 2:
                    raise IntentBusError(f"Network error during {method} {endpoint}: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s

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
        res = self._request(
            "POST", 
            "/intent", 
            json={"goal": goal, "payload": payload, "reward": reward}
        )
        return res.json()

    def claim(self, goal=None):
        """Claim the next available intent. Returns None if queue is empty."""
        params = {"goal": goal} if goal else None
        res = self._request("POST", "/claim", params=params)
        if res.status_code == 204:
            return None
        return res.json()

    def fulfill(self, intent_id):
        """Mark an intent as fulfilled."""
        res = self._request("POST", f"/fulfill/{intent_id}")
        return res.json()

    def set(self, key, value, ttl=600):
        """Store a value in the ephemeral key-value store."""
        res = self._request(
            "POST", 
            f"/set/{key}", 
            json={"value": value, "ttl": ttl}
        )
        return res.json()

    def get(self, key):
        """Retrieve a value from the ephemeral key-value store."""
        res = self._request("GET", f"/get/{key}")
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
                    try:
                        handler(job["payload"])
                        self.fulfill(job["id"])
                        print(f"[IntentBus] Fulfilled {job['id']}")
                    except Exception as handler_err:
                        print(f"[IntentBus] Handler failed for {job['id']}: {handler_err}")
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
            
