import argparse
import json
import logging
import sys
import time
from typing import Any

from intent_bus import IntentBusError, IntentClient, WorkerRuntime
from intent_bus.exceptions import IntentBusLeaseLostError
from intent_bus.version import __version__


def log(level: str, event: str, message: str = '', silent: bool = False):
    if silent and level.lower() not in ('error', 'crit', 'critical'):
        return
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] {level.upper():<5} | {event:<12} | {message}')


def _redact_payload(payload: Any) -> Any:
    """
    Mask sensitive fields to prevent accidental credential leaks in CI/CD logs.
    """
    sensitive_keys = {
        'secret',
        'token',
        'api_key',
        'apikey',
        'password',
        'passwd',
        'auth',
        'credential',
        'credentials',
        'private_key',
    }

    def is_sensitive_key(key: Any) -> bool:
        k = str(key).strip().lower()
        return (
            k in sensitive_keys
            or k.endswith('_secret')
            or k.endswith('_token')
            or k.endswith('_key')
            or k.endswith('_password')
            or k.endswith('_passwd')
            or k.endswith('_auth')
            or k.endswith('_credential')
            or k.endswith('_credentials')
            or k.endswith('_private_key')
        )

    if isinstance(payload, dict):
        redacted = {}
        for k, v in payload.items():
            if is_sensitive_key(k):
                redacted[k] = '********'
            else:
                redacted[k] = _redact_payload(v)
        return redacted

    if isinstance(payload, list):
        return [_redact_payload(item) for item in payload]

    return payload


def main():
    parser = argparse.ArgumentParser(
        prog='intent-bus',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Intent Bus CLI | Protocol v2.1\n"
            "A professional toolkit for interacting with the Intent Bus distributed job system."
        ),
        epilog=(
            "Examples:\n"
            "  # Start a worker for image processing with GPU capabilities\n"
            "  intent-bus listen resize_image -n media -c gpu,cuda\n"
            "  \n"
            "  # Publish a high-priority job with a 10s delay\n"
            "  intent-bus publish send_email '{\"to\":\"user@ex.com\"}' --priority 900 --delay 10\n"
            "  \n"
            "  # Check the status of a specific intent\n"
            "  intent-bus status <intent_id>\n"
            "  \n"
            "  # Retrieve the result of a fulfilled intent\n"
            "  intent-bus result <intent_id>\n"
            "\n"
            "Environment Variables:\n"
            "  INTENT_API_KEY      Your API key (or place it in ~/.apikey)\n"
        ),
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'intent-bus {__version__}',
        help='Show the SDK version and exit'
    )

    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        '-s', '--silent',
        action='store_true',
        help='Suppress non-critical logs and payload dumps',
    )

    subparsers = parser.add_subparsers(dest='command', title='commands')

    # --- LISTEN COMMAND ---
    listen_parser = subparsers.add_parser(
        'listen',
        parents=[base_parser],
        help='Start a worker node to claim and process intents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Polls the server for eligible intents. Honors server-directed backoffs.",
    )
    listen_parser.add_argument('goal', help='The intent goal to claim (e.g., "process_image")')
    listen_parser.add_argument('-n', '--namespace', default='default', help='Routing namespace (default: default)')
    listen_parser.add_argument('-w', '--worker-id', help='Explicit worker identity for tracking')
    listen_parser.add_argument('-c', '--capabilities', help='Comma-separated capabilities (e.g., "gpu,ocr")')
    listen_parser.add_argument('--publisher', help='Only claim intents published by this API key')
    listen_parser.add_argument('--once', action='store_true', help='Process exactly one job and exit')
    listen_parser.add_argument('--interval', type=float, default=5.0, help='Base polling interval in seconds (default: 5.0)')
    listen_parser.add_argument('--show-payload', action='store_true', help='Print unredacted JSON payloads (WARNING: may leak secrets)')

    # --- PUBLISH COMMAND ---
    pub_parser = subparsers.add_parser(
        'publish',
        parents=[base_parser],
        help='Publish a new intent to the bus',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Push a new JSON payload to the bus for workers to claim.",
    )
    pub_parser.add_argument('goal', help='The goal/target for this intent')
    pub_parser.add_argument('data', help='Strict JSON payload string (must use double quotes for keys)')
    pub_parser.add_argument('-n', '--namespace', default='default', help='Routing namespace (default: default)')
    pub_parser.add_argument('-p', '--public', action='store_true', help='Make intent visible across all namespaces')
    pub_parser.add_argument('--priority', type=int, default=100, help='Priority (0-1000, higher is first. Default: 100)')
    pub_parser.add_argument('--delay', type=float, default=0.0, help='Delay execution by X seconds (Default: 0.0)')
    pub_parser.add_argument('--max-attempts', type=int, default=3, help='Max claim attempts before moving to dead-letter (Default: 3)')
    pub_parser.add_argument('--backoff', type=float, default=5.0, help='Exponential backoff base in seconds (Default: 5.0)')
    pub_parser.add_argument('--target', help='Restrict claim to a specific worker ID')
    pub_parser.add_argument('--capability', help='Require a specific worker capability')
    pub_parser.add_argument('--idempotency', help='Provide a custom idempotency key')

    # --- STATUS COMMAND ---
    status_parser = subparsers.add_parser(
        'status',
        parents=[base_parser],
        help='Check the current status of an intent',
    )
    status_parser.add_argument('intent_id', help='The ID of the intent to check')

    # --- RESULT COMMAND ---
    result_parser = subparsers.add_parser(
        'result',
        parents=[base_parser],
        help='Retrieve the result of a fulfilled intent',
    )
    result_parser.add_argument('intent_id', help='The ID of the intent to retrieve')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    is_silent = getattr(args, 'silent', False)

    logging.basicConfig(
        level=logging.ERROR if is_silent else logging.INFO,
        format='[%(asctime)s] %(levelname)-5s | %(name)s | %(message)s',
        datefmt='%H:%M:%S',
    )

    if is_silent:
        logging.disable(logging.WARNING)

    try:
        client = IntentClient()
    except IntentBusError as e:
        log('crit', 'auth_fail', str(e), is_silent)
        sys.exit(1)

    # --- COMMAND: LISTEN ---
    if args.command == 'listen':
        caps = (
            [c.strip() for c in args.capabilities.split(',') if c.strip()]
            if getattr(args, 'capabilities', None)
            else None
        )

        def process_job(payload: Any) -> dict:
            if not is_silent:
                border = '─' * 40
                print(f'\n{border}')
                display_payload = payload if getattr(args, 'show_payload', False) else _redact_payload(payload)
                print(json.dumps(display_payload, indent=2, ensure_ascii=False, default=str))
                print(f'{border}\n')
            return {'status': 'processed_by_cli'}

        if args.once:
            job = client.claim(
                goal=args.goal,
                namespace=args.namespace,
                worker_id=args.worker_id,
                capabilities=caps,
                publisher=getattr(args, 'publisher', None),
            )

            if job:
                log('info', 'claiming', f'ID: {job.id}', is_silent)
                try:
                    res = process_job(job.payload)
                    client.fulfill(
                        intent_id=job.id,
                        claim_token=job.claim_token,
                        result=res,
                    )
                    log('info', 'fulfilled', f'ID: {job.id}', is_silent)

                except IntentBusLeaseLostError as e:
                    log('error', 'lease_lost', str(e), is_silent)

                except Exception as e:
                    log('error', 'handler_err', str(e), is_silent)
                    try:
                        client.fail(
                            intent_id=job.id,
                            claim_token=job.claim_token,
                            error=str(e),
                        )
                    except IntentBusLeaseLostError as fail_err:
                        log('error', 'lease_lost', str(fail_err), is_silent)
                    except Exception as fail_err:
                        log('error', 'fail_err', str(fail_err), is_silent)

            else:
                log('info', 'idle', f'No jobs found for {args.goal}.', is_silent)

            return

        runtime = WorkerRuntime(
            client=client,
            worker_id=args.worker_id,
            capabilities=caps,
            poll_interval=args.interval,
            close_client=True,
        )

        log('info', 'worker_up', f'Target: {args.namespace}/{args.goal}', is_silent)
        runtime.listen(
            goal=args.goal,
            handler=process_job,
            namespace=args.namespace,
        )

    # --- COMMAND: PUBLISH ---
    elif args.command == 'publish':
        try:
            payload = json.loads(args.data)
            res = client.publish(
                goal=args.goal,
                payload=payload,
                namespace=args.namespace,
                visibility='public' if args.public else 'private',
                priority=args.priority,
                delay=args.delay,
                max_attempts=args.max_attempts,
                backoff_base=args.backoff,
                target_worker=args.target,
                required_capability=args.capability,
                idempotency_key=args.idempotency,
            )
            if res:
                log('info', 'pub_done', f'ID: {res.id} | Status: {res.status}', is_silent)
            else:
                log('error', 'pub_fail', 'Server rejected the intent.', is_silent)
        except json.JSONDecodeError:
            log('error', 'json_err', 'Invalid JSON payload. Ensure keys are double-quoted.', is_silent)
        except IntentBusError as e:
            log('error', 'pub_err', str(e), is_silent)

    # --- COMMAND: STATUS ---
    elif args.command == 'status':
        try:
            status = client.get_status(args.intent_id)
            if status:
                log('info', 'status', f'ID: {status.id} | State: {status.status} | Goal: {status.goal}', is_silent)
                if status.error:
                    log('warn', 'error', f'Last Error: {status.error}', is_silent)
            else:
                log('error', 'not_found', f'Intent {args.intent_id} not found.', is_silent)
        except IntentBusError as e:
            log('error', 'api_err', str(e), is_silent)

    # --- COMMAND: RESULT ---
    elif args.command == 'result':
        try:
            res = client.get_result(args.intent_id)
            if res:
                log('info', 'result', f'ID: {res.id} | Type: {res.result_type}', is_silent)
                border = '─' * 40
                print(f'\n{border}')
                print(json.dumps(res.result, indent=2, ensure_ascii=False, default=str))
                print(f'{border}\n')
            else:
                log('error', 'not_found', f'Result for {args.intent_id} not found or not fulfilled.', is_silent)
        except IntentBusError as e:
            log('error', 'api_err', str(e), is_silent)


if __name__ == '__main__':
    main()
