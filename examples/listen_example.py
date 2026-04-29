from intent_bus import IntentClient

# Host and Auth automatically resolve. Absolute zero friction.
bus = IntentClient()

def handle_notification(payload):
    print(f"Received: {payload['message']}")

bus.listen(goal="send_notification", handler=handle_notification)
