# Intent Bus SDK

[![PyPI version](https://badge.fury.io/py/intent-bus.svg)](https://badge.fury.io/py/intent-bus)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python SDK for **Intent Bus**, a lightweight distributed job bus implementing the **Intent Protocol v7.5**.

> **Looking for the server?**  
> This repository contains the Python SDK and Worker Runtime.  
> Protocol server implementation: https://github.com/dsecurity49/Intent-Bus

---

##  Quickstart (30 seconds)

### 1. Install
```bash
pip install intent-bus
```

### 2. Publish an intent
```python
from intent_bus import IntentClient

bus = IntentClient()

bus.publish(
    goal="notify",
    payload={"message": "Hello World"},
    namespace="default"
)
```

### 3. Run a worker
```python
from intent_bus import IntentClient

bus = IntentClient()

def handler(payload):
    print("Received:", payload)
    return {"status": "done"}

bus.listen(
    goal="notify",
    handler=handler,
    namespace="default"
)
```

Done. You now have a working distributed job pipeline.

---

## Versioning Model

- **SDK Version:** `v1.3.0`
- **Protocol Version:** `Intent Protocol v7.5`

The SDK evolves independently while maintaining compatibility with the stable protocol specification.

---

## New in SDK v1.3.0 (Protocol v7.5 Support)

- First-Class CLI – Run workers and publish intents directly from the terminal
- Namespace Routing – Isolated execution domains for intents
- Structured Fulfillment – Workers can return structured metadata
- Reliable Claim Model – Safe at-least-once execution with retry awareness
- Server-driven Backoff – Respects Retry-After headers for idle scaling

---

## Installation

```bash
pip install intent-bus
```

---

## Command Line Interface (CLI)

The SDK includes a production-ready CLI for both workers and publishers.

### Start a worker node

```bash
intent-bus listen notify --namespace prod --worker-id worker-01
```

### With capabilities

```bash
intent-bus listen notify \
  --namespace prod \
  --worker-id worker-01 \
  --capabilities python,notify
```

### Publish an intent

```bash
intent-bus publish notify '{"message": "Hello World"}' --namespace prod
```

### Publish publicly

```bash
intent-bus publish notify '{"message": "Hello World"}' --namespace prod --public
```

> WARNING: Always wrap JSON payloads in single quotes in shells (Termux/Linux especially).

---

## Automatic Credential Resolution

1. Constructor:
   ```python
   IntentClient(api_key="...")
   ```
2. Environment:
   ```bash
   export INTENT_API_KEY="..."
   ```
3. Local file:
   ```
   ~/.apikey (chmod 600 required)
   ```

---

## SDK Usage

### Worker (Consumer)

```python
from intent_bus import IntentClient

bus = IntentClient()

def handle_task(payload):
    print(f"Processing: {payload}")

    return {
        "status": "success",
        "processed_by": "worker-01"
    }

bus.listen(
    goal="video_render",
    handler=handle_task,
    namespace="heavy-tasks",
    capabilities="gpu,ffmpeg"
)
```

---

### Handler Semantics

| Return Value | Meaning |
|------|--------|
| dict | Structured fulfill payload |
| True / None | Default fulfillment |
| False | Mark job as failed |

---

### Publisher (Producer)

```python
bus.publish(
    goal="video_render",
    payload={"id": 101, "format": "mp4"},
    namespace="heavy-tasks",
    visibility="private"
)
```

---

## CLI Worker Behavior

- Workers poll continuously for jobs
- Server controls idle backoff via Retry-After
- At-least-once delivery model
- Workers must be idempotent

---

## Core Concepts

### Namespaces

- default -> general queue
- prod -> production workloads
- heavy-tasks -> compute-heavy workloads

Namespaces are enforced server-side as routing isolation domains.

---

### Workers

Workers:
- claim jobs
- execute handlers
- report success/failure

Identified by:
- worker_id
- capabilities

---

### Capabilities

Example:

```
python,notify,gpu,ffmpeg
```

Used to filter eligible workers.

---

## Error Handling

The SDK raises structured exceptions for predictable failure handling.

### Exception Types

| Exception | When it occurs |
|----------|----------------|
| `IntentBusAuthError` | Invalid API key, authentication failure |
| `IntentBusRateLimitError` | Server rate limit exceeded (HTTP 429) |
| `IntentBusError` | General SDK or server-side error |

---

### Example: Safe Error Handling

```python
from intent_bus import IntentClient
from intent_bus.exceptions import (
    IntentBusError,
    IntentBusAuthError,
    IntentBusRateLimitError
)

bus = IntentClient()

try:
    result = bus.publish(
        goal="notify",
        payload={"message": "hello"}
    )
except IntentBusAuthError:
    print("Invalid API key")
except IntentBusRateLimitError:
    print("Rate limited, retry later")
except IntentBusError as e:
    print(f"General SDK error: {e}")
```

---

## Reliability Model

| Property | Behavior |
|----------|----------|
| Delivery | At-least-once |
| Retry | SDK + server retry support |
| Claim | Atomic fetch |
| Fulfill | Final state transition |
| Idle | Retry-After backoff |

Workers must be idempotent.

---

## Security Model

- Payloads are untrusted input
- Never expose secrets in intents
- Public intents are broadcast to fleet
- API key required for all mutations

---

## Safety Guarantees

| Operation | Behavior |
|----------|----------|
| publish | Idempotent |
| set | Idempotent KV store |
| claim | Atomic |
| fulfill | Final |
| fail | Terminal |

---

## Failure Handling

- Network failures retry where safe
- claim is not retried automatically
- server may return 204 + Retry-After
- failed jobs may enter dead-letter state

---

## License

MIT License © 2026 dsecurity49
