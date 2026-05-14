import argparse
import json
import sys
import time
import logging
from typing import Any

from intent_bus import IntentClient, WorkerRuntime, IntentBusError

def log(level: str, event: str, message: str = '', silent: bool = False):
    if silent and level.lower() not in ('error', 'crit'):
        return
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] {level.upper():<5} | {event:<12} | {message}')

def main():
    parser = argparse.ArgumentParser(
        prog='intent-bus', 
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Intent Bus CLI | Protocol v2.0\n"
            "A lightweight, distributed job bus toolkit."
        ),
        epilog=(
            "examples:\n"
            "  intent-bus listen process_image -c gpu,ocr\n"
            "  intent-bus publish process_image '{\"url\": \"https://...\"}' -p\n"
            "\n"
            "environment variables:\n"
            "  INTENT_API_KEY      Your API key (or place it in ~/.apikey)\n"
        )
    )
    
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('-s', '--silent', action='store_true', help='Suppress non-critical logs, payloads, and network warnings')

    subparsers = parser.add_subparsers(dest='command', title='commands')

    listen_parser = subparsers.add_parser(
        'listen', 
        parents=[base_parser],
        help='Start a worker node loop to claim and process intents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Start a continuous worker polling loop. Honors server-directed backoffs.",
        epilog="example:\n  intent-bus listen encode_video -n media -c ffmpeg,gpu --interval 2.5"
    )
    listen_parser.add_argument('goal', help='The specific intent goal to claim (e.g., process_image)')
    listen_parser.add_argument('-n', '--namespace', default='default', help='Routing namespace (default: default)')
    listen_parser.add_argument('-w', '--worker-id', help='Explicit worker identity for tracking')
    listen_parser.add_argument('-c', '--capabilities', help='Comma-separated worker capabilities (e.g., gpu,ocr)')
    listen_parser.add_argument('--once', action='store_true', help='Process exactly one job and exit immediately')
    listen_parser.add_argument('--interval', type=float, default=5.0, help='Base polling interval in seconds (default: 5.0)')

    pub_parser = subparsers.add_parser(
        'publish', 
        parents=[base_parser],
        help='Publish a new intent to the bus',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Push a new JSON payload to the bus for workers to claim.",
        epilog="example:\n  intent-bus publish send_email '{\"to\": \"user@ext.com\"}' -n comms"
    )
    pub_parser.add_argument('goal', help='The goal/target for this intent')
    pub_parser.add_argument('data', help='Strict JSON payload string (must use double quotes for keys)')
    pub_parser.add_argument('-n', '--namespace', default='default', help='Routing namespace (default: default)')
    pub_parser.add_argument('-p', '--public', action='store_true', help='Make intent visible across all namespaces')

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)

    is_silent = getattr(args, 'silent', False)

    logging.basicConfig(
        level=logging.ERROR if is_silent else logging.INFO,
        format='[%(asctime)s] %(levelname)-5s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    if is_silent:
        logging.disable(logging.WARNING)

    try:
        client = IntentClient()
    except IntentBusError as e:
        log('crit', 'auth_fail', str(e), is_silent)
        sys.exit(1)

    caps = ([c.strip() for c in args.capabilities.split(',') if c.strip()] if args.capabilities else None)

    if args.command == 'listen':
        def process_job(payload: Any) -> dict:
            if not is_silent:
                border = '─' * 40
                print(f'\n{border}')
                print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
                print(f'{border}\n')
            return {'status': 'processed_by_cli'}

        if args.once:
            job = client.claim(
                goal=args.goal, 
                namespace=args.namespace, 
                worker_id=args.worker_id, 
                capabilities=caps
            )
            
            if job:
                log('info', 'claiming', f'ID: {job.id}', is_silent)
                try:
                    res = process_job(job.payload)
                    client.fulfill(job.id, result=res)
                    log('info', 'fulfilled', f'ID: {job.id}', is_silent)
                except Exception as e:
                    log('error', 'handler_err', str(e), is_silent)
                    client.fail(job.id, error=str(e))
            else:
                log('info', 'idle', f'No jobs found for {args.goal}.', is_silent)
            return

        runtime = WorkerRuntime(
            client=client,
            worker_id=args.worker_id,
            capabilities=caps,
            poll_interval=args.interval,
            close_client=True
        )

        log('info', 'worker_up', f'Target: {args.namespace}/{args.goal}', is_silent)
        runtime.listen(
            goal=args.goal,
            handler=process_job,
            namespace=args.namespace
        )

    elif args.command == 'publish':
        try:
            payload = json.loads(args.data)
            res = client.publish(
                goal=args.goal, 
                payload=payload, 
                namespace=args.namespace, 
                visibility='public' if args.public else 'private'
            )
            if res: 
                log('info', 'pub_done', f'ID: {res.id}', is_silent)
            else:
                log('error', 'pub_fail', 'Server rejected the intent.', is_silent)
        except json.JSONDecodeError:
            log('error', 'json_err', 'Invalid JSON payload. Ensure keys are double-quoted.', is_silent)
        except IntentBusError as e:
            log('error', 'pub_err', str(e), is_silent)

if __name__ == '__main__':
    main()
