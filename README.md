# Intent Bus SDK

[![PyPI version](https://badge.fury.io/py/intent-bus.svg)](https://badge.fury.io/py/intent-bus) [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python SDK for **Intent Bus**, a lightweight distributed job bus implementing the **Intent Protocol v2.0**. 

Intent Bus is designed for environments where network reliability is not guaranteed. It features a decentralized worker architecture, strict namespace isolation, optional shared KV state, resilient HTTP transports, and strict data contracts.

> **Looking for the server?**
> This repository contains the Python SDK and Worker Runtime.
> Protocol server implementation: https://github.com/dsecurity49/Intent-Bus

---

## ⚠️ Upgrading from v1.x? Breaking Changes

If you are migrating existing workers or publishers from SDK v1.x to v2.x, you must update your code to handle the new strict data models and method signatures.

**1. The `fulfill` Method Signature**
You can no longer unpack dictionaries directly into the `fulfill` method. You must explicitly use the `result` keyword argument.
* **Bad (v1.x):** `client.fulfill(job.id, **{"status": "done"})`
* **Good (v2.x):** `client.fulfill(job.id, result={"status": "done"})`

**2. Strongly Typed Job Models**
The SDK no longer returns raw dictionaries. `client.claim()` returns a strongly typed `ClaimResponse` wrapper. You must use dot-notation to access job attributes.
* **Bad (v1.x):** `payload = job["payload"]`
* **Good (v2.x):** `payload = job.payload`

**3. Strict JSON Enforcement**
The SDK now actively blocks Python `NaN` and `Infinity` values from being serialized into payloads to maintain strict compliance with the JSON RFC.

---

## What's New in SDK v2.0.3?

The V2.0 architecture has been rewritten for production stability:
* **Resilient Transport:** Built-in connection pooling and full-jitter retry backoff.
* **Strict Immutable Models:** Payloads are parsed into frozen dataclasses (`ClaimedIntent`, `IntentStatus`, `IntentResult`) to prevent silent protocol drift.
* **Worker Orchestration:** The new `WorkerRuntime` class handles queue draining, server-directed backoffs, and error isolation.
* **State Management:** Native support for the Intent Bus Key-Value (KV) store for shared worker state.
* **Hardened CLI:** A built-in terminal interface with a silent mode for daemonized environments.

---

## Quickstart

### 1. Install
```bash
pip install intent-bus
```

### 2. Configure Authentication
The SDK automatically resolves your API key from the environment.
```bash
export INTENT_API_KEY="tk_your_api_key_here"
# Alternatively, place it in ~/.apikey
```

### 3. Publish an Intent
```python
from intent_bus import IntentClient

with IntentClient() as client:
    # Intents have strict namespace-scoped isolation by default
    job = client.publish(
        goal="process_image",
        payload={"url": "s3://bucket/image1.png"},
        namespace="media",
        priority=100
    )
    print(f"Published Job ID: {job.id}")
```

### 4. Run a Worker
The `WorkerRuntime` manages resilient polling, allowing you to focus on business logic.

```python
from typing import Any
from intent_bus import IntentClient, WorkerRuntime

def image_handler(payload: Any) -> dict:
    print(f"Processing: {payload.get('url')}")
    # When using WorkerRuntime, returning a supported result payload automatically fulfills the intent.
    return {"result": {"status": "success", "file": "out.png"}, "result_type": "json"}

client = IntentClient()
runtime = WorkerRuntime(client=client, capabilities=["gpu", "ffmpeg"])

# Blocks and listens indefinitely, honoring server backoffs
runtime.listen(
    goal="process_image",
    handler=image_handler,
    namespace="media"
)
```

---

## Advanced Usage

### Targeted Routing & Priorities
You can restrict which workers are allowed to claim an intent, or schedule it for the future.

```python
client.publish(
    goal="train_model",
    payload={"epochs": 50},
    namespace="ml",
    priority=999,                    # 0 to 1000 (Highest)
    delay=3600.0,                    # Delay execution by 1 hour
    required_capability="a100_gpu",  # Only workers with this cap can claim
    target_worker="node-alpha-01",   # Strict single-node targeting
    max_attempts=5                   # Allow 5 retry attempts if workers crash
)
```

### Shared State (Key-Value Store)
Workers can share lightweight state via the built-in KV store (best-effort distributed cache). JSON-serializable data is handled safely for transport.

```python
# Set a configuration that expires in 1 hour (3600s)
client.set("model_weights_version", {"v": "2.4.1", "path": "/models/v2"}, ttl=3600)

# Retrieve it from another worker
config = client.get("model_weights_version")
print(config["path"])
```

### Manual Lifecycle Control
If you bypass `WorkerRuntime` and build your own polling loop using `client.claim()`, you must manage the intent's lifecycle explicitly:

```python
job = client.claim(goal="encode", namespace="media")

if job:
    # 1. Need more time? Extend the server lease
    client.extend_claim(job.id, seconds=300) 
    
    try:
        do_heavy_work(job.payload)
        # 2. Mark successful
        client.fulfill(job.id, result="Done", result_type="text")
    except Exception as e:
        # 3. Explicitly fail the job (re-queues the intent if server retry attempts remain)
        client.fail(job.id, error=str(e))
```

### Retrieving Results
Check the status or fetch the final result of a processed intent.

```python
status = client.get_status("intent_id_here")
print(status.status) # 'open', 'claimed', 'fulfilled', 'dead'

if status.status == 'fulfilled':
    result = client.get_result("intent_id_here")
    print(result.result) # The output payload from the worker
    print(result.completed_at)
```

---

## Command Line Interface (CLI)

The SDK ships with a production-ready CLI.

### Run a Worker Node
```bash
intent-bus listen process_image --namespace media --worker-id node-01 -c gpu,ffmpeg
```

**CLI Flags:**
* `-s, --silent`: Suppress payload dumps and non-critical runtime logs for cleaner terminal output.
* `--once`: Claim exactly one job, process it, and exit immediately.
* `--interval`: Base polling interval in seconds (default: 5.0).

### Publish via CLI
Intents have strict namespace-scoped isolation by default.
```bash
intent-bus publish process_image '{"url": "https://..."}' --namespace media
```
*Note: Ensure JSON payloads use double quotes (`"`) inside single quotes (`'`) to avoid shell parsing errors.*

**Publish Publicly (Cross-Namespace):**
Use `-p` or `--public` to broadcast the intent to any worker looking for that goal, regardless of namespace.
```bash
intent-bus publish send_email '{"to": "user@ext.com"}' -n comms --public
```

---

## Error Handling & Resilience

The SDK raises structured exceptions for predictable failure handling. Transport timeouts and connection drops are gracefully handled internally by full-jitter backoff algorithms, but persistent failures will surface to your code.

| Exception | Cause |
|----------|----------------|
| `IntentBusAuthError` | Invalid API key or signature verification failure. |
| `IntentBusRateLimitError` | Server rate limit exceeded (HTTP 429). |
| `IntentBusNetworkError` | Timeouts, DNS failures, connection drops after all retries exhaust. |
| `IntentBusProtocolError` | Server violated RFC schema (caught by strict data models). |
| `IntentBusError` | Base SDK exception (e.g., payload validation errors). |

---

## License

MIT License © 2026 dsecurity49
