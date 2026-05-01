# Intent Bus SDK 🚌

[![PyPI version](https://img.shields.io/pypi/v/intent-bus.svg)](https://pypi.org/project/intent-bus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python client for the **Intent Protocol**.

> **Looking for the server?** > This repository contains only the Python SDK.  
> To self-host the bus, see the main project:  
> [https://github.com/dsecurity49/Intent-Bus](https://github.com/dsecurity49/Intent-Bus)

---

## 🚀 What is Intent Bus?

Intent Bus is a lightweight, decentralized job execution protocol designed for backend automation and distributed architecture.

* **Publish tasks from anywhere**
* **Execute them on any machine**
* **No external queues required** (Perfect for self-hosted or single-node deployments)

### 🛠️ SDK Features
* **Secure Auth:** Request signing via HMAC-SHA256 (Strict Mode).
* **Resilience:** Automatic retries for safe, idempotent operations.
* **Zero-Config:** Automatic discovery of API keys from environment or local files.
* **Hybrid Routing:** Support for both private and public "Open Fleet" intents.

---

## 📦 Installation

```bash
pip install intent-bus
```

---

## 🔐 Zero-Config Authentication

The SDK automatically resolves your API key in this priority order:

1.  Explicit `api_key` argument in the constructor.
2.  `INTENT_API_KEY` environment variable.
3.  Local file: `~/.apikey`

**Quick Setup:**
```bash
echo "your_api_key_here" > ~/.apikey
chmod 600 ~/.apikey
```

---

## ⚡ Quickstart

```python
from intent_bus import IntentClient

# Host and Auth automatically resolve. Absolute zero friction.
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

# Blocking loop that polls the bus for work
bus.listen(goal="notify", handler=handle_notification)
```

---

## 🗃️ 3. Ephemeral Key-Value Store

```python
# Store data with an optional TTL (seconds)
bus.set("last_sync_time", "1682800000", ttl=600)

# Retrieve data
timestamp = bus.get("last_sync_time")
```

---

## 🔁 Retry & Safety Behavior

| Operation | Retries | Safe? |
| :--- | :--- | :--- |
| `publish` | ✅ Yes | Yes (Idempotent) |
| `set` | ✅ Yes | Yes (Idempotent) |
| `get` | ✅ Yes | Yes |
| `claim` | ❌ No | No (State-changing poll) |
| `fulfill` | ❌ No | No (State-changing) |
| `fail` | ❌ No | No (State-changing) |

---

## 🔒 Security Model

The SDK uses **Strict Authentication** via HMAC-SHA256 to ensure:
* **Replay Protection:** Unique nonces and timestamps.
* **Request Integrity:** Signed paths and bodies.
* **Identity Verification:** Cryptographic proof of API key ownership.

---

## ⚠️ Security Warning: Public Intents

If you set `visibility="public"`, **any worker on the Open Fleet can claim and read your payload.**

**Never include sensitive data in public intents:**
* ❌ API Keys / Passwords
* ❌ Personally Identifiable Information (PII)
* ❌ Private infrastructure details

---

## 🧠 Design Principles

* **Protocol First:** The SDK is just a wrapper; the protocol is pure HTTP/JSON.
* **Zero-Ops:** Deploy a bus and a worker in seconds.
* **At-Least-Once Delivery:** Workers are expected to be idempotent.
* **Stateless Execution:** Workers don't need to maintain local state between jobs.

---

## 📜 License

MIT License © 2026 Dsecurity
