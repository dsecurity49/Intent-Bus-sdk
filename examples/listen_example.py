from intent_bus import IntentClient

bus = IntentClient(
    host="https://dsecurity.pythonanywhere.com",
    api_key="your_key_here"
)

def handle_notification(payload):
    print(f"Received: {payload['message']}")

bus.listen(goal="send_notification", handler=handle_notification)
