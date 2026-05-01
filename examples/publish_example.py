import argparse
from intent_bus import IntentClient

# Initialize client (resolves ~/.apikey or INTENT_API_KEY)
bus = IntentClient()

def main():
    parser = argparse.ArgumentParser(description="Intent Bus | Publish Example")
    
    # CLI Arguments
    parser.add_argument("--message", "-m", default="Hello from the SDK", help="The notification message")
    parser.add_argument("--public", "-p", action="store_true", help="Make this intent visible to the public fleet")
    
    args = parser.parse_args()

    # Determine visibility based on the --public flag
    visibility = "public" if args.public else "private"

    print(f"[*] Publishing {visibility} intent...")

    payload = {
        "message": args.message,
        "source": "cli_example"
    }

    # v1.2.0: visibility routing enabled
    result = bus.publish(
        goal="send_notification",
        payload=payload,
        visibility=visibility
    )

    print(f"[+] Published! ID: {result.get('id')}")
    print(f"    Visibility: {visibility.upper()}")

if __name__ == "__main__":
    main()
