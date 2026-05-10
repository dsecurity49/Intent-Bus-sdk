import argparse
from intent_bus import IntentClient

bus = IntentClient()

def main():
    parser = argparse.ArgumentParser(description="Intent Bus | Publish Example")

    parser.add_argument("--message", "-m", default="Hello from the SDK")
    parser.add_argument("--public", "-p", action="store_true")
    parser.add_argument("--namespace", "-n", default="default")

    args = parser.parse_args()

    visibility = "public" if args.public else "private"

    print(f"[*] Publishing intent → namespace='{args.namespace}', visibility='{visibility}'")

    payload = {
        "message": args.message,
        "source": "cli_example"
    }

    result = bus.publish(
        goal="send_notification",
        payload=payload,
        visibility=visibility,
        namespace=args.namespace
    )

    if result and isinstance(result, dict):
        print(f"[+] Published! ID: {result.get('id')}")
        print(f"    Visibility: {visibility.upper()}")
        print(f"    Namespace: {args.namespace}")
    else:
        print("[-] Publish failed or no response returned.")

if __name__ == "__main__":
    main()
