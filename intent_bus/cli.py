import argparse
import json
import sys
import time
from typing import Any, Dict, Optional, Union
from intent_bus import IntentClient

def log(level: str, event: str, message: str = ""):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {level.upper():<5} | {event:<12} | {message}")

def get_job_field(job: Any, key: str, default: Any = None) -> Any:
    if isinstance(job, dict):
        return job.get(key, default)
    return getattr(job, key, default)

def main():
    parser = argparse.ArgumentParser(prog="intent-bus", description="Intent Bus CLI | Hardened Production Worker Runtime")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    listen_parser = subparsers.add_parser("listen", help="Start a worker node loop")
    listen_parser.add_argument("goal", help="The intent goal to process")
    listen_parser.add_argument("-n", "--namespace", default="default")
    listen_parser.add_argument("-w", "--worker-id")
    listen_parser.add_argument("-c", "--capabilities")
    listen_parser.add_argument("--once", action="store_true")
    listen_parser.add_argument("--interval", type=float, default=5.0)

    pub_parser = subparsers.add_parser("publish", help="Publish a new intent to the bus")
    pub_parser.add_argument("goal")
    pub_parser.add_argument("data")
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

    if args.command == "listen":
        def process_job(job: Any) -> bool:
            job_id = get_job_field(job, "id")
            if not job_id: return False
            log("info", "claiming", f"ID: {job_id}")
            
            try:
                payload = get_job_field(job, "payload", {})
                print("\n" + "─" * 40 + f"\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n" + "─" * 40)
                result = {"status": "processed_by_cli"}
            except Exception as e:
                log("error", "handler_err", str(e))
                client.fail(job_id, str(e))
                return False

            client.fulfill(job_id, **result)
            log("info", "fulfilled", f"ID: {job_id}")
            return True

        if args.once:
            job = client.claim(args.goal, namespace=args.namespace, worker_id=args.worker_id, capabilities=args.capabilities)
            if job and job.status_code == 200 and get_job_field(job, "id"):
                process_job(job)
            else:
                log("info", "idle", "No jobs found.")
            return

        log("info", "worker_up", f"Target: {args.namespace}/{args.goal}")
        try:
            while True:
                job = client.claim(args.goal, namespace=args.namespace, worker_id=args.worker_id, capabilities=args.capabilities)
                if not job or job.status_code == 204 or not get_job_field(job, "id"):
                    delay = float(get_job_field(job, "retry_after") or args.interval)
                    time.sleep(delay)
                    continue
                process_job(job)
                time.sleep(0.5)
        except KeyboardInterrupt:
            log("info", "shutdown", "Worker detached")

    elif args.command == "publish":
        try:
            res = client.publish(args.goal, json.loads(args.data), namespace=args.namespace, visibility="public" if args.public else "private")
            if res: log("info", "pub_done", f"ID: {res.get('id')}")
        except Exception as e:
            log("error", "pub_err", str(e))
