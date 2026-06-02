'''Worker orchestration and polling runtime.'''

import logging
import random
import time
from typing import Any, Callable, Optional, Sequence, Union

from ..client.sync import IntentClient
from ..constants import DEFAULT_POLL_INTERVAL, MAX_POLL_BACKOFF
from ..exceptions import (
    IntentBusError,
    IntentBusLeaseLostError,
)

logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(
        self,
        client: IntentClient,
        worker_id: Optional[str] = None,
        capabilities: Optional[Union[str, Sequence[str]]] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_backoff: float = MAX_POLL_BACKOFF,
        close_client: bool = False,
    ):
        self.client = client
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.poll_interval = poll_interval
        self.max_backoff = max_backoff
        self.close_client = close_client

    def _execute_with_retry(
        self,
        operation: str,
        func: Callable[[], Any],
        max_attempts: int = 3,
        base_delay: float = 2.0,
    ) -> bool:
        '''
        Execute a network mutation with exponential backoff.

        v2.1 semantics:
        - HTTP 404 means lease ownership is lost
        - lease-loss MUST abort retries immediately
        '''

        attempt = 0
        delay = base_delay

        while attempt < max_attempts:
            try:
                func()
                return True

            except IntentBusLeaseLostError:
                logger.warning(
                    '[%s] Lease lost. Aborting retry.', operation
                )
                return False

            except IntentBusError as e:
                logger.warning(
                    '[%s] Network attempt %d failed: %s',
                    operation,
                    attempt + 1,
                    e,
                )

            except Exception as e:
                logger.warning(
                    '[%s] Unexpected attempt %d failed: %s',
                    operation,
                    attempt + 1,
                    e,
                )

            attempt += 1

            if attempt < max_attempts:
                time.sleep(delay + random.uniform(0, 0.5))
                delay *= 2

        logger.error(
            '[%s] Operation failed after %d attempts',
            operation,
            max_attempts,
        )

        return False

    def listen(
        self,
        goal: str,
        handler: Callable[[Any], Any],
        namespace: str = 'default',
        full_envelope: bool = False,
    ) -> None:

        consecutive_errors = 0

        if isinstance(self.capabilities, str):
            caps_display = self.capabilities
        elif self.capabilities:
            caps_display = ','.join(self.capabilities)
        else:
            caps_display = 'none'

        logger.info(
            "Worker online. Listening on: '%s/%s' | capabilities: '%s'",
            namespace,
            goal,
            caps_display,
        )

        try:
            while True:
                try:
                    job = self.client.claim(
                        goal=goal,
                        namespace=namespace,
                        worker_id=self.worker_id,
                        capabilities=self.capabilities,
                    )

                    # No work available
                    if not job or job.status_code == 204:
                        consecutive_errors = 0

                        wait_time = (
                            float(job.retry_after)
                            if job and job.retry_after is not None
                            else self.poll_interval
                        )

                        time.sleep(wait_time)
                        continue

                    consecutive_errors = 0

                    job_id = job.get('id')
                    claim_token = job.get('claim_token')

                    if not job_id or not claim_token:
                        logger.error(
                            'Claimed job missing id or claim_token. Skipping.'
                        )
                        continue

                    try:
                        if full_envelope:
                            payload_to_pass = (
                                job.data.to_dict()
                                if job.data
                                else {}
                            )
                        else:
                            payload_to_pass = job.get('payload', {})

                        result = handler(payload_to_pass)

                        # Only literal False means explicit rejection
                        if result is False:
                            self._execute_with_retry(
                                'fail',
                                lambda: self.client.fail(
                                    intent_id=job_id,
                                    claim_token=claim_token,
                                    error='Worker handler returned False',
                                ),
                            )

                        else:
                            # Determine fulfillment payload
                            if result is None:
                                safe_kwargs = {}
                            elif isinstance(result, dict) and (
                                'result' in result or 'result_type' in result
                            ):
                                safe_kwargs = {
                                    k: v for k, v in result.items()
                                    if k in {'result', 'result_type'}
                                }
                                if 'result_type' in safe_kwargs and 'result' not in safe_kwargs:
                                    raise ValueError(
                                        "Handler returned 'result_type' without a 'result'"
                                    )
                            else:
                                safe_kwargs = {'result': result}

                            self._execute_with_retry(
                                'fulfill',
                                lambda: self.client.fulfill(
                                    intent_id=job_id,
                                    claim_token=claim_token,
                                    **safe_kwargs,
                                ),
                            )

                    except ValueError as handler_exc:
                        logger.error(
                            'Handler returned invalid protocol shape: %s',
                            handler_exc,
                        )

                        self._execute_with_retry(
                            'fail',
                            lambda: self.client.fail(
                                intent_id=job_id,
                                claim_token=claim_token,
                                error=str(handler_exc),
                            ),
                        )

                    except Exception as handler_exc:
                        logger.exception('Worker handler crashed')

                        self._execute_with_retry(
                            'fail',
                            lambda: self.client.fail(
                                intent_id=job_id,
                                claim_token=claim_token,
                                error=str(handler_exc),
                            ),
                        )

                except (KeyboardInterrupt, SystemExit):
                    raise

                except Exception as e:
                    consecutive_errors += 1

                    sleep_time = min(
                        self.poll_interval * (2 ** consecutive_errors),
                        self.max_backoff,
                    )

                    sleep_time += random.uniform(0, 0.5)

                    if consecutive_errors <= 3:
                        logger.warning(
                            'Runtime error: %s. Backing off for %.2fs',
                            e,
                            sleep_time,
                        )
                    else:
                        logger.debug(
                            'Runtime error: %s. Backing off for %.2fs',
                            e,
                            sleep_time,
                        )

                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info('Shutting down Intent Bus worker cleanly.')

        finally:
            if self.close_client:
                self.client.close()
                logger.info('Transport session closed.')
