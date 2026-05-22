import argparse
import json
import logging
import sys
import time
from typing import Any

from intent_bus import IntentBusError, IntentClient, WorkerRuntime
from intent_bus.exceptions import IntentBusLeaseLostError


def log(level: str, event: str, message: str = '', silent: bool = False):
    if silent and level.lower() not in ('error', 'crit', 'critical'):
        return
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] {level.upper():<5} | {event:<12} | {message}')


def _redact_payload(payload: Any) -> Any:
    """
    Mask sensitive fields to prevent accidental credential leaks in CI/CD logs.

    Redacts common secret-like keys while avoiding overly broad matches
    such as 'monkey' or 'keypad'.
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
            "A lightweight, distributed job bus toolkit."
        ),
        epilog=(
            "examples:\n"
            "  intent-bus listen process_image -c gpu,ocr\n"
            "  intent-bus publish process_image '{\"url\": \"https://...\"}' -p\n"
            "\n"
            "environment variables:\n"
            "  INTENT_API_KEY      Your API key (or place it in ~/.apikey)\n"
        ),
    )

    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        '-s', '--silent',
        action='store_true',
        help='Suppress non-critical logs, payloads, and network warnings',
    )

    subparsers = parser.add_subparsers(dest='command', title='commands')

    listen_parser = subparsers.add_parser(
        'listen',
        parents=[base_parser],
        help='Start a worker node loop to claim and process intents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Start a continuous worker polling loop. Honors server-directed backoffs.",
        epilog="example:\n  intent-bus listen encode_video -n media -c ffmpeg,gpu --interval 2.5",
    )
    listen_parser.add_argument('goal', help='The specific intent goal to claim (e.g., process_image)')
    listen_parser.add_argument('-n', '--namespace', default='default', help='Routing namespace (default: default)')
    listen_parser.add_argument('-w', '--worker-id', help='Explicit worker identity for tracking')
    listen_parser.add_argument('-c', '--capabilities', help='Comma-separated worker capabilities (e.g., gpu,ocr)')
    listen_parser.add_argument('--once', action='store_true', help='Process exactly one job and exit immediately')
    listen_parser.add_argument('--interval', type=float, default=5.0, help='Base polling interval in seconds (default: 5.0)')
    listen_parser.add_argument('--show-payload', action='store_true', help='Print full, unredacted JSON payloads (WARNING: may leak secrets)')

    pub_parser = subparsers.add_parser(
        'publish',
        parents=[base_parser],
        help='Publish a new intent to the bus',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Push a new JSON payload to the bus for workers to claim.",
        epilog="example:\n  intent-bus publish send_email '{\"to\": \"user@ext.com\"}' -n comms",
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
        datefmt='%H:%M:%S',
    )

    if is_silent:
        logging.disable(logging.WARNING)

    try:
        client = IntentClient()
    except IntentBusError as e:
        log('crit', 'auth_fail', str(e), is_silent)
        sys.exit(1)

    caps = (
        [c.strip() for c in args.capabilities.split(',') if c.strip()]
        if getattr(args, 'capabilities', None)
        else None
    )

    if args.command == 'listen':
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

    elif args.command == 'publish':
        try:
            payload = json.loads(args.data)
            res = client.publish(
                goal=args.goal,
                payload=payload,
                namespace=args.namespace,
                visibility='public' if args.public else 'private',
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
