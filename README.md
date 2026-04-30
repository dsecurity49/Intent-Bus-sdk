Intent Bus SDK 🚌




The official Python client for the Intent Protocol.

> Looking for the server?
This repository contains only the Python SDK.
To self-host the bus, see the main project:
https://github.com/dsecurity49/Intent-Bus




---

🚀 What is Intent Bus?

Intent Bus is a lightweight, decentralized job execution protocol.

Publish tasks from anywhere

Execute them on any machine

No queues, brokers, or infrastructure required


This SDK provides:

Secure request signing (HMAC-SHA256)

Automatic retries (where safe)

Polling + worker loop abstraction

Zero-config authentication



---

📦 Installation

pip install intent-bus


---

🔐 Zero-Config Authentication

The SDK automatically resolves your API key in this order:

1. Explicit api_key argument


2. INTENT_API_KEY environment variable


3. Local file: ~/.apikey



Example:

echo "your_api_key_here" > ~/.apikey  
chmod 600 ~/.apikey


---

⚡ Quickstart

from intent_bus import IntentClient  
  
bus = IntentClient()


---

📤 1. Publishing an Intent (Producer)

result = bus.publish(  
    goal="notify",  
    payload={"message": "System backup complete."}  
)  
  
print(f"Dispatched Intent ID: {result['id']}")


---

📥 2. Listening for Intents (Worker)

def handle_notification(payload):  
    print(f"Received: {payload['message']}")  
  
bus.listen(goal="notify", handler=handle_notification)


---

🗃️ 3. Ephemeral Key-Value Store

bus.set("last_sync_time", "1682800000", ttl=600)  
timestamp = bus.get("last_sync_time")


---

⚙️ Advanced Usage

Custom Hosts (Self-Hosting)

bus = IntentClient(  
    base_url="https://your-private-bus.com",  
    api_key="your_key"  
)


---

Strict Idempotency

bus.publish(  
    goal="process_payment",  
    payload={"user": "alice", "amount": 50},  
    idempotency_key="tx_987654321"  
)


---

🔁 Retry Behavior

Operation	Retries	Reason

publish	✅ Yes	Idempotent
set	✅ Yes	Idempotent
get	✅ Yes	Safe read
claim	❌ No	State-changing
fulfill	❌ No	Prevent duplicates
fail	❌ No	Prevent duplicates



---

🔒 Security Model

Strict Authentication (HMAC-SHA256):

X-API-KEY

X-Timestamp

X-Nonce

X-Signature


Provides:

Replay protection

Integrity

Authenticity



---

⚠️ Worker Safety

Workers MUST be idempotent

Do NOT execute raw user input blindly

Prefer whitelisting

Avoid storing secrets in payloads



---

❗ Error Handling

from intent_bus import (  
    IntentBusError,  
    IntentBusAuthError,  
    IntentBusRateLimitError  
)


---

🧪 Minimal Example

from intent_bus import IntentClient  
  
bus = IntentClient()  
  
def handler(payload):  
    print("Job:", payload)  
  
bus.listen(goal="test", handler=handler)


---

🧠 Design Principles

Protocol First

Zero-Ops

At-Least-Once Delivery

Explicit Failures



---

📜 License

MIT License © 2026 Dsecurity

And check yourself in all the codes if they are consistent
