from intent_bus import IntentClient

# Host and Auth automatically resolve from ~/.apikey or INTENT_API_KEY env.
# Absolute zero friction.
bus = IntentClient()

def handle_notification(payload):
    """
    Standard handler for 'send_notification' intents.
    """
    # Defensive check for the expected payload key
    message = payload.get("message", "No content")
    print(f"[Worker] Received Notification: {message}")

if __name__ == "__main__":
    # Start the blocking listen loop for a specific goal
    bus.listen(goal="send_notification", handler=handle_notification)
