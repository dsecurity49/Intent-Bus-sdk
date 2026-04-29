from intent_bus import IntentClient

bus = IntentClient(
    host="https://dsecurity.pythonanywhere.com",
    api_key="your_key_here"
)

result = bus.publish(
    goal="send_notification",
    payload={"message": "Hello from the SDK"}
)
print(f"Published: {result}")
