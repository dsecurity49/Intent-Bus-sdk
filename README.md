# Intent Bus SDK 🚌

[![PyPI version](https://img.shields.io/pypi/v/intent-bus.svg)](https://pypi.org/project/intent-bus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python client for the **Intent Protocol**.

> **Looking for the server?**  
> This repository contains only the Python SDK.  
> To self-host the bus, see the main project:  
> https://github.com/dsecurity49/Intent-Bus

---

## 🚀 What is Intent Bus?

Intent Bus is a lightweight, decentralized job execution protocol.

- Publish tasks from anywhere  
- Execute them on any machine  
- No queues, brokers, or infrastructure required  

This SDK provides:
- Secure request signing (HMAC-SHA256)
- Automatic retries (where safe)
- Polling + worker loop abstraction
- Zero-config authentication

---

## 📦 Installation

```bash
pip install intent-bus
```

---

## 🔐 Zero-Config Authentication

The SDK automatically resolves your API key in this order:

1. Explicit `api_key` argument  
2. `INTENT_API_KEY` environment variable  
3. Local file: `~/.apikey`  

Example:

```bash
echo "your_api_key_here" > ~/.apikey
chmod 600 ~/.apikey
```

---

## ⚡ Quickstart

```python
from intent_bus import IntentClient

bus = IntentClient()
```

---

## 📤 1. Publishing an Intent (Producer)

```python
result = bus.publish(
    goal="notify",
    payload={"message": "System backup complete."}
)

print(f"Dispatched Intent ID: {result['id']}")
```

---

## 📥 2. Listening for Intents (Worker)

```python
def handle_notification(payload):
    print(f"Received: {payload['message']}")

bus.listen(goal="notify", handler=handle_notification)
```

---

## 🗃️ 3. Ephemeral Key-Value Store

```python
bus.set("last_sync_time", "1682800000", ttl=600)
timestamp = bus.get("last_sync_time")
```

---

## ⚙️ Advanced Usage

### Custom Hosts (Self-Hosting)

```python
bus = IntentClient(
    base_url="https://your-private-bus.com",
    api_key="your_key"
)
```

---

### Strict Idempotency

```python
bus.publish(
    goal="process_payment",
    payload={"user": "alice", "amount": 50},
    idempotency_key="tx_987654321"
)
```

---

## 🔁 Retry Behavior

| Operation  | Retries | Reason |
|-----------|--------|--------|
| publish   | ✅ Yes | Idempotent |
| set       | ✅ Yes | Idempotent |
| get       | ✅ Yes | Safe read |
| claim     | ❌ No  | State-changing |
| fulfill   | ❌ No  | Prevent duplicates |
| fail      | ❌ No  | Prevent duplicates |

---

## 🔒 Security Model

Strict Authentication (HMAC-SHA256):

- X-API-KEY  
- X-Timestamp  
- X-Nonce  
- X-Signature  

Provides:
- Replay protection  
- Integrity  
- Authenticity  

---

## ⚠️ Worker Safety

- Workers MUST be idempotent  
- Do NOT execute raw user input blindly  
- Prefer whitelisting  
- Avoid storing secrets in payloads  

---

## ❗ Error Handling

```python
from intent_bus import (
    IntentBusError,
    IntentBusAuthError,
    IntentBusRateLimitError
)
```

---

## 🧪 Minimal Example

```python
from intent_bus import IntentClient

bus = IntentClient()

def handler(payload):
    print("Job:", payload)

bus.listen(goal="test", handler=handler)
```

---

## 🧠 Design Principles

- Protocol First  
- Zero-Ops  
- At-Least-Once Delivery  
- Explicit Failures  

---

## 📜 License

MIT License © 2026 Dsecurity
