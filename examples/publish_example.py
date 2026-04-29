from intent_bus import IntentClient

# Host and Auth automatically resolve. Absolute zero friction.
bus = IntentClient()

result = bus.publish(
    goal="send_notification",
    payload={"message": "Hello from the SDK"}
)
print(f"Published: {result}")
