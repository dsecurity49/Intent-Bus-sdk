# Intent Bus SDK 

[![PyPI version](https://img.shields.io/pypi/v/intent-bus.svg)](https://pypi.org/project/intent-bus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python client for **Intent Bus**, the reference implementation of the **Intent Protocol**.

> **Looking for the server?**
> This repository contains only the Python SDK.  
> To self-host the bus or view the protocol source, see the main project:  
> [https://github.com/dsecurity49/Intent-Bus](https://github.com/dsecurity49/Intent-Bus)

---

##  What is Intent Bus?

Intent Bus is a lightweight, decentralized job execution protocol designed for backend automation and distributed architecture. It allows you to dispatch "intents" (tasks) from one machine and have them executed by workers on any other machine without managing a complex message broker.

 **Delivery Guarantee:** **At-least-once execution.** Due to the nature of distributed polling, duplicate executions are possible. Workers **MUST** be idempotent.

###  Design Principles
* **Protocol First:** The SDK is a convenience wrapper; the core protocol is pure HTTP/JSON.
* **Zero-Ops:** Designed for instant deployment without managing RabbitMQ, Redis, or Kafka.
* **Stateless Workers:** Workers do not need to maintain local state between jobs.
* **Explicit Failure:** No silent drops; jobs are explicitly fulfilled, failed, or timed out.

---

##  Installation

```bash
pip install intent-bus
```

---

## 🔐 Automatic Credential Resolution

The SDK resolves your API key automatically using the following priority:
1.  **Constructor:** `IntentClient(api_key="...")`
2.  **Environment:** `export INTENT_API_KEY="..."`
3.  **Local File:** `~/.apikey` (Must be restricted: `chmod 600 ~/.apikey`)

---

##  Quickstart

###  The Minimal Worker
```python
from intent_bus import IntentClient

bus = IntentClient()

def handler(payload):
    print("Received Job:", payload)

bus.listen(goal="test", handler=handler)
```

---

##  1. Publishing an Intent (Producer)

By default, intents are private to your API key. v1.2.0 introduces **Hybrid Routing** for public tasks.

```python
# Standard Private Intent (Private Fleet)
result = bus.publish(
    goal="notify",
    payload={"message": "System backup complete."}
)

# Public Intent (Open Fleet)
# WARNING: Public intents are broadcast to all workers and must be treated as public internet data.
bus.publish(
    goal="resize_image",
    payload={"url": "https://img.com/cat.jpg"},
    visibility="public"
)
```

---

##  2. Listening for Intents (Worker)

Workers poll the bus for work. The `handler` determines the job's final state via its return value.

```python
def handle_notification(payload):
    if not payload.get("message"):
        return False # Explicit failure reported to bus
    print(f"Received: {payload['message']}")
    return True # Fulfillment reported to bus

# Start the blocking poll loop
bus.listen(goal="notify", handler=handle_notification)
```

---

##  3. Ephemeral Key-Value Store

Used for sharing temporary state or configuration between distributed workers.

```python
# Set with a 10-minute expiry (600s)
bus.set("node_01_status", "active", ttl=600)

# Retrieve
status = bus.get("node_01_status")
```

---

##  Advanced Usage

### Custom Hosts (Self-Hosting)
```python
bus = IntentClient(
    base_url="https://your-private-bus.com",
    api_key="your_key",
    timeout=15.0
)
```

### Strict Idempotency
To prevent double-execution under **at-least-once delivery semantics**, pass a unique key.
```python
bus.publish(
    goal="charge_user",
    payload={"amount": 50},
    idempotency_key="tx_order_9982"
)
```

---

##  Operation Safety Table

| Operation | SDK Retries | Protocol Safety |
| :--- | :--- | :--- |
| `publish` | ✅ Yes | Idempotent via `idempotency_key` |
| `set` | ✅ Yes | Idempotent via `idempotency_key` |
| `get` | ✅ Yes | Safe (Read-only) |
| `claim` | ❌ No | State-changing; Non-idempotent |
| `fulfill` | ❌ No | State-changing; Non-idempotent |
| `fail` | ❌ No | State-changing; Non-idempotent |

---

##  Failure Model & Reliability

* **Worker Crashes:** If a worker crashes mid-execution, the intent remains "claimed" until the visibility timeout expires, after which it returns to the queue.
* **Network Timeouts:** Timeouts during `fulfill` can lead to duplicate executions. Consumers **must** handle this via local state or idempotent logic.
* **Dead Letters:** Jobs that fail repeatedly are marked as failed. Use the Admin Dashboard (/admin/dashboard) to monitor dead letters and investigate failures.

---

## 🔒 Security Guidelines

### ⚠️ Public Intent Warning
Setting `visibility="public"` broadcasts your payload to the Open Fleet.
* **NEVER** include passwords, tokens, or private PII.
* **ALWAYS** assume the worker executing a public job is an untrusted third party.

###  Worker Best Practices
* **Defensive Parsing:** Always validate `payload` structure before processing.
* **Non-Interactive:** Prefer whitelisting commands over executing raw strings.
* **Isolation:** Treat all payloads as untrusted data, especially in Open Fleet mode.

###  Request Integrity
The SDK uses **HMAC-SHA256** signatures for all requests, providing:
* **Authentication:** Verification of API key ownership.
* **Integrity:** Protection against tampering of paths and payloads.
* **Replay Protection:** Unique nonces and timestamps per request.

---

##  Raw HTTP Example (Protocol First)

You don't need the SDK to use the Intent Protocol.
```bash
curl -X POST https://dsecurity.pythonanywhere.com/intent \
  -H "X-API-KEY: your_key" \
  -H "Content-Type: application/json" \
  -d '{"goal":"test","payload":{"msg":"hello"}}'
```

---

## ❗ Error Handling

```python
from intent_bus import (
    IntentBusError,
    IntentBusAuthError,
    IntentBusRateLimitError
)

try:
    bus.publish("goal", {"data": 1})
except IntentBusAuthError:
    # Handle bad credentials or signature failure
except IntentBusRateLimitError:
    # Handle 429 Too Many Requests
```

---

##  License

MIT License © 2026 Dsecurity
