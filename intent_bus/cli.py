import argparse
import json
import sys
import time
from typing import Any, Dict, Optional, Union
from intent_bus import IntentClient

def log(level: str, event: str, message: str = ""):
    """Standardized telemetry layer."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {level.upper():<5} | {event:<12} | {message}")

def get_job_field(job: Any, key: str, default: Any = None) -> Any:
    """Safety layer for dict/object access during protocol migration."""
    if isinstance(job, dict):
        return job.get(key, default)
    return getattr(job, key, default)

def main():
    parser = argparse.ArgumentParser(
        prog="intent-bus",
        description="Intent Bus CLI | Production Worker Runtime"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Listen Configuration
    listen_parser = subparsers.add_parser("listen", help="Start worker node")
    listen_parser.add_argument("goal", help="Intent goal")
    listen_parser.add_argument("-n", "--namespace", default="default")
    listen_parser.add_argument("-w", "--worker-id")
    listen_parser.add_argument("-c", "--capabilities")
    listen_parser.add_argument("--once", action="store_true")
    listen_parser.add_argument("--interval", type=float, default=5.0)

    # Publish Configuration
    pub_parser = subparsers.add_parser("publish", help="Publish intent")
    pub_parser.add_argument("goal")
    pub_parser.add_argument("data", help="JSON string")
    pub_parser.add_argument("-n", "--namespace", default="default")
    pub_parser.add_argument("-p", "--public", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        client = IntentClient()
    except Exception as e:
        log("crit", "init_fail", str(e))
        sys.exit(1)

    normalized_caps = None
    if args.command == "listen" and args.capabilities:
        normalized_caps = ",".join([c.strip() for c in args.capabilities.split(",") if c.strip()])

    if args.command == "listen":
        def cli_handler(payload: Any) -> Union[Dict[str, Any], bool]:
            """
            v7.5 Handler Semantics:
            - dict -> structured fulfill
            - False -> explicit fail
            - True/None -> default fulfill
            """
            try:
                print("\n" + "─" * 40)
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                print("─" * 40)
                return {
                    "result": {"status": "processed_by_cli"},
                    "result_type": "json",
                }
            except Exception as e:
                log("error", "handler_err", str(e))
                return False

        def process_job(job: Any) -> bool:
            job_id = get_job_field(job, "id", "unknown")
            payload = get_job_field(job, "payload", {})

            log("info", "claiming", f"ID: {job_id}")
            result = cli_handler(payload)

            if result is False:
                client.fail(job_id, "CLI processing failure")
                log("warn", "job_failed", f"ID: {job_id}")
                return False

            fulfill_data = result if isinstance(result, dict) else {}
            client.fulfill(job_id, **fulfill_data)
            log("info", "fulfilled", f"ID: {job_id}")
            return True

        if args.once:
            job = client.claim(args.goal, namespace=args.namespace, worker_id=args.worker_id, capabilities=normalized_caps)
            if job is None:
                log("error", "net_error", "Server unreachable")
                sys.exit(1)

            # Safety check using helper for status_code
            status_code = get_job_field(job, "status_code", 200)
            if status_code == 204:
                retry_after = get_job_field(job, "retry_after", "N/A")
                log("info", "idle", f"Backoff: {retry_after}s")
                return

            process_job(job)
            return

        log("info", "worker_up", f"{args.namespace}/{args.goal}")
        try:
            while True:
                job = client.claim(args.goal, namespace=args.namespace, worker_id=args.worker_id, capabilities=normalized_caps)

                if job is None:
                    log("error", "conn_err", f"Retrying in {args.interval}s")
                    time.sleep(args.interval)
                    continue

                status_code = get_job_field(job, "status_code", 200)
                if status_code == 204:
                    retry_after = get_job_field(job, "retry_after")
                    try:
                        delay = float(retry_after) if retry_after else args.interval
                    except (TypeError, ValueError):
                        delay = args.interval
                    time.sleep(delay)
                    continue

                # SUCCESS PATH: Process job and use adaptive pacing (0.5s)
                process_job(job)
                time.sleep(0.5) 

        except KeyboardInterrupt:
            log("info", "shutdown", "Worker detached")
            sys.exit(0)

    elif args.command == "publish":
        try:
            payload = json.loads(args.data)
            visibility = "public" if args.public else "private"
            result = client.publish(args.goal, payload, namespace=args.namespace, visibility=visibility)
            if result:
                log("info", "pub_done", f"ID: {result.get('id')}")
            else:
                log("error", "pub_fail", "No response")
        except Exception as e:
            log("error", "pub_err", str(e))
            sys.exit(1)
