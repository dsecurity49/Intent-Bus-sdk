'''Worker orchestration and polling runtime.'''
import logging
import random
import time
from typing import Any, Callable, Dict, Optional, Sequence, Union

from ..client.sync import IntentClient
from ..constants import DEFAULT_POLL_INTERVAL, MAX_POLL_BACKOFF

logger = logging.getLogger(__name__)

class WorkerRuntime:
    def __init__(
        self, client: IntentClient, worker_id: Optional[str] = None,
        capabilities: Optional[Union[str, Sequence[str]]] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL, max_backoff: float = MAX_POLL_BACKOFF,
        close_client: bool = False
    ):
        self.client = client
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.poll_interval = poll_interval
        self.max_backoff = max_backoff
        self.close_client = close_client

    def listen(self, goal: str, handler: Callable[[Any], Any], namespace: str = 'default', full_envelope: bool = False) -> None:
        consecutive_errors = 0
        
        if isinstance(self.capabilities, str):
            caps_display = self.capabilities
        elif self.capabilities:
            caps_display = ','.join(self.capabilities)
        else:
            caps_display = 'none'

        logger.info(f"Worker online. Listening on: '{namespace}/{goal}' | capabilities: '{caps_display}'")

        try:
            while True:
                try:
                    job = self.client.claim(
                        goal=goal, namespace=namespace, worker_id=self.worker_id, capabilities=self.capabilities,
                    )

                    if not job or job.status_code == 204:
                        consecutive_errors = 0
                        try:
                            wait_time = float(job.retry_after) if job and job.retry_after is not None else self.poll_interval
                        except (TypeError, ValueError):
                            wait_time = self.poll_interval
                        time.sleep(wait_time)
                        continue

                    consecutive_errors = 0
                    job_id = job.get('id')
                    
                    if not job_id:
                        logger.error('Claimed job has no ID, skipping.')
                        continue

                    try:
                        if full_envelope:
                            payload_to_pass = job.data.to_dict() if job.data else {}
                        else:
                            payload_to_pass = job.get('payload', {})
                            
                        result = handler(payload_to_pass)

                        if result is False:
                            try: self.client.fail(job_id, error='Worker handler returned False')
                            except Exception: logger.exception('Failed to report handler rejection')
                        else:
                            safe_kwargs = {}
                            if result is None:
                                pass
                            elif isinstance(result, dict) and ('result' in result or 'result_type' in result):
                                allowed = {'result', 'result_type'}
                                safe_kwargs = {k: v for k, v in result.items() if k in allowed}
                                
                                if 'result_type' in safe_kwargs and 'result' not in safe_kwargs:
                                    raise ValueError("Handler returned 'result_type' without a 'result'")
                            else:
                                safe_kwargs = {'result': result}
                                
                            try:
                                self.client.fulfill(job_id, **safe_kwargs)
                            except Exception:
                                logger.exception('Failed to report fulfillment')

                    except ValueError as handler_exc:
                        logger.error(f'Handler returned invalid protocol shape: {handler_exc}')
                        try: self.client.fail(job_id, error=str(handler_exc))
                        except Exception: logger.exception('Failed to report execution failure')
                    except Exception as handler_exc:
                        logger.exception('Worker handler crashed')
                        try: self.client.fail(job_id, error=str(handler_exc))
                        except Exception: logger.exception('Failed to report execution failure')

                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    sleep_time = min(self.poll_interval * (2 ** consecutive_errors), self.max_backoff)
                    sleep_time += random.uniform(0, 0.5) 
                    
                    if consecutive_errors <= 3:
                        logger.warning(f'Runtime error: {e}. Backing off for {sleep_time:.2f}s')
                    else:
                        logger.debug(f'Runtime error: {e}. Backing off for {sleep_time:.2f}s')
                        
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info('Shutting down Intent Bus worker cleanly.')
        finally:
            if self.close_client:
                self.client.close()
                logger.info('Transport session closed.')
