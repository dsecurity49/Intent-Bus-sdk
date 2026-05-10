from intent_bus import IntentClient

bus = IntentClient()

def handle_notification(payload):
    """
    Handler for send_notification intents.

    Return False → skip fulfill
    Return dict/None → fulfill job
    """
    message = (payload or {}).get("message", "No content")
    print(f"[Worker] Received Notification: {message}")

    return {
        "result": "delivered",
        "result_type": "text"
    }

if __name__ == "__main__":
    print("Starting Intent Bus v7.5 worker node...")

    bus.listen(
        goal="send_notification",
        handler=handle_notification,
        namespace="default",
        worker_id="python-worker-1",
        capabilities="python,notify",
        poll_interval=5.0
    )
