# Intent Bus SDK 🚌

[![PyPI version](https://badge.fury.io/py/intent-bus.svg)](https://badge.fury.io/py/intent-bus)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The official Python client for the **[Intent-Bus Protocol](https://github.com/dsecurity49/Intent-Bus)**. 

> **Looking for the server code?** > This repository is strictly the Python client SDK. If you want to host your own decentralized job bus, head over to the main **[Intent-Bus Core Repository](https://github.com/dsecurity49/Intent-Bus)**.

Intent-Bus is a decentralized, BYOC (Bring Your Own Compute) automation protocol. This SDK allows you to easily publish tasks to your bus and spin up background workers on any machine with just a few lines of code.

## Installation

```bash
pip install intent-bus
```

## Zero-Config Authentication

The client automatically connects to the global public bus (`dsecurity.pythonanywhere.com`) and looks for your API key in the following order:
1. Explicitly passed `api_key` argument.
2. The `INTENT_API_KEY` environment variable.
3. A local `~/.apikey` file.

If you have your key saved in `~/.apikey`, you can run the bus with zero configuration.

## Quickstart

```python
from intent_bus import IntentClient

# Automatically uses dsecurity.pythonanywhere.com and your local ~/.apikey
bus = IntentClient()
```

### 1. Publishing an Intent (The Producer)
Send data to the bus from any script, webhook, or server.

```python
result = bus.publish(
    goal="notify",
    payload={"message": "System backup complete."}
)
print(f"Dispatched Intent ID: {result['id']}")
```

### 2. Listening for Intents (The Consumer)
Turn any machine into a background worker. The `listen` method automatically handles polling, network retries, claim locks, and fulfillment.

```python
def trigger_alert(payload):
    print(f"Alert received: {payload['message']}")

bus.listen(goal="notify", handler=trigger_alert)
```

### 3. Ephemeral Store
The SDK also supports interacting with the Intent-Bus fast key-value store.

```python
# Set a value with a 10-minute TTL
bus.set("last_sync_time", "1682800000", ttl=600)

# Retrieve the value
timestamp = bus.get("last_sync_time")
```

## Custom Hosts (Self-Hosting)
If you are running your own private Intent-Bus server, simply pass your URL during initialization:

```python
bus = IntentClient(host="[https://your-private-bus.com](https://your-private-bus.com)", api_key="your_key")
```

## Error Handling
The SDK raises explicit exceptions for easy debugging:
* `IntentBusAuthError`: Invalid or missing API key.
* `IntentBusRateLimitError`: Too many requests within the 60-second window.
* `IntentBusError`: Base class for other HTTP or routing failures.
