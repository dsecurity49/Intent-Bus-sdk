import math
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from intent_bus import IntentClient, WorkerRuntime
from intent_bus.exceptions import (
    IntentBusAuthError,
    IntentBusError,
    IntentBusLeaseLostError,
    IntentBusNetworkError,
    IntentBusProtocolError,
    IntentBusRateLimitError,
)
from intent_bus.models.intent import ClaimedIntent


@pytest.fixture
def client():
    return IntentClient(api_key="test_key")


# =================================================================
# 1. AUTHENTICATION & INIT TESTS
# =================================================================

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("INTENT_API_KEY", raising=False)
    with patch("os.path.exists", return_value=False):
        with pytest.raises(IntentBusAuthError, match="No API key found"):
            IntentClient()


def test_auth_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 401
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusAuthError):
            client.publish("goal", {})


# =================================================================
# 2. MODEL INTEGRITY & FORWARDING TESTS (V2.1)
# =================================================================

def test_claimed_intent_strict_validation():
    """Ensure the v2.1 ClaimedIntent model enforces claim_token existence."""
    valid_data = {
        "id": "123",
        "goal": "test",
        "claim_token": "token_abc123",
        "payload": {}
    }
    intent = ClaimedIntent.from_dict(valid_data)
    assert intent.claim_token == "token_abc123"

    invalid_data = {
        "id": "123",
        "goal": "test",
        "payload": {}
    }  # Missing token
    with pytest.raises(IntentBusProtocolError, match="Protocol Error: 'claim_token' must be a string"):
        ClaimedIntent.from_dict(invalid_data)


def test_claim_response_attribute_forwarding(client):
    """Ensure ClaimResponse does not mask underlying AttributeErrors."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "id": "job1", "goal": "test", "claim_token": "token", "payload": {}
    }

    with patch("requests.Session.request", return_value=mock_res):
        job = client.claim(goal="test")
        
        # 1. Valid forwarding (dunder __getattr__ bypass)
        assert job.id == "job1"
        assert job.claim_token == "token"
        
        # 2. Missing attribute should explicitly bubble up
        with pytest.raises(AttributeError):
            _ = job.non_existent_field


# =================================================================
# 3. PUBLISHING TESTS
# =================================================================

def test_publish_success(client):
    mock_res = MagicMock()
    mock_res.status_code = 201
    mock_res.json.return_value = {"id": "abc123", "status": "published", "goal": "test_goal"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        result = client.publish("test_goal", {"key": "value"}, namespace="custom")

        assert result.id == "abc123"

        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"namespace":"custom"' in sent_body


def test_unserializable_payload(client):
    """V2.1 strict JSON testing including NaN guards."""
    class Unserializable:
        pass

    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad": Unserializable()})

    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad": math.nan})


# =================================================================
# 4. CLAIMING TESTS
# =================================================================

def test_claim_204_no_content(client):
    """Claim returns a ClaimResponse object even on 204."""
    mock_res = MagicMock()
    mock_res.status_code = 204
    mock_res.headers = {"Retry-After": "15"}

    with patch("requests.Session.request", return_value=mock_res):
        result = client.claim(goal="test_goal")

        assert not result  # bool() resolves to False because data is None
        assert result.status_code == 204
        assert result.retry_after == 15.0


def test_claim_routing_headers(client):
    """Ensure worker-id and capabilities are passed in headers."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "id": "job1",
        "goal": "test_goal",
        "claim_token": "mock_token",
        "payload": {}
    }

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.claim(
            goal="test_goal",
            worker_id="test-worker",
            capabilities=["gpu", "ocr"]
        )

        _, kwargs = mock_req.call_args
        headers = kwargs.get("headers", {})
        assert headers["X-Worker-ID"] == "test-worker"
        assert headers["X-Worker-Capabilities"] == "gpu,ocr"


def test_canonical_path_query_sorting(client):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "id": "job1",
        "goal": "test_goal",
        "claim_token": "mock_token",
        "payload": {}
    }
    mock_res.headers = {} 

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.claim(goal="test_goal")

        args, kwargs = mock_req.call_args
        assert "goal=test_goal&namespace=default" in args[1]


# =================================================================
# 5. MUTATION & TOKEN ISOLATION TESTS (V2.1)
# =================================================================

def test_fulfill_with_payload_and_token(client):
    """Test that fulfill correctly injects the claim_token into the payload."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"status": "ok"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.fulfill(
            intent_id="job123",
            claim_token="secret_lease_token",
            result={"status": "success", "code": 200}
        )

        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"claim_token":"secret_lease_token"' in sent_body
        assert '"code":200' in sent_body
        assert '"status":"success"' in sent_body
        assert '"result_type":"json"' in sent_body


def test_extend_claim_with_token(client):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"status": "ok"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.extend_claim(
            intent_id="job123",
            claim_token="secret_lease_token",
            seconds=120
        )

        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"claim_token":"secret_lease_token"' in sent_body
        assert '"seconds":120' in sent_body


def test_lease_lost_error_mapping(client):
    """Ensure HTTP 404s on lease-mutation endpoints raise IntentBusLeaseLostError."""
    mock_res = MagicMock()
    mock_res.status_code = 404
    mock_res.json.return_value = {"error": {"message": "Lease not found"}}
    mock_res.headers = {}

    # Fulfill (mutating endpoint) -> Should raise LeaseLostError
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusLeaseLostError, match="Lease not found"):
            client.fulfill("job123", claim_token="bad_token", result={})

    # Status (read-only endpoint) -> Should raise standard IntentBusError strictly
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusError) as exc_info:
            client.get_status("job123")
        assert type(exc_info.value) is IntentBusError 


# =================================================================
# 6. TRANSPORT & RETRY TESTS
# =================================================================

def test_rate_limit_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 429
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusRateLimitError):
            client.publish("goal", {})


@patch("time.sleep", return_value=None)
def test_network_retry(mock_sleep, client):
    """Explicitly isolates network errors and tests retry counts without halting CI."""
    # Claim (POST) should NOT retry by default (retries=0)
    with patch("requests.Session.request", side_effect=requests.ConnectionError("Net Error")) as mock_req:
        with pytest.raises(IntentBusNetworkError):
            client.claim("test_goal")
        assert mock_req.call_count == 1

    # Publish defaults to 2 retries (3 total attempts)
    with patch("requests.Session.request", side_effect=requests.ConnectionError("Net Error")) as mock_req:
        with pytest.raises(IntentBusNetworkError):
            client.publish("test_goal", {})
        assert mock_req.call_count == 3
        # Should have slept twice for the 2 retries
        assert mock_sleep.call_count == 2


# =================================================================
# 7. WORKER RUNTIME INTEGRATION TESTS (V2.1)
# =================================================================

def test_worker_runtime_abort_on_lease_loss(client):
    """Ensure WorkerRuntime aborts network retries immediately if lease is lost."""
    runtime = WorkerRuntime(client=client, poll_interval=0.1)
    mock_func = MagicMock(side_effect=IntentBusLeaseLostError("404 Lease Lost"))

    # Execute with retry should return False and only try ONCE
    result = runtime._execute_with_retry("fulfill", mock_func, max_attempts=3, base_delay=0.01)

    assert result is False
    assert mock_func.call_count == 1


@patch("time.sleep", return_value=None)
def test_worker_runtime_retry_on_network_error(mock_sleep, client):
    """Ensure WorkerRuntime retries on standard network/server errors."""
    runtime = WorkerRuntime(client=client, poll_interval=0.1)

    # Fail twice, succeed on third attempt
    mock_func = MagicMock(side_effect=[IntentBusError("500 Error"), IntentBusError("502 Error"), True])
    result = runtime._execute_with_retry("fail", mock_func, max_attempts=3, base_delay=0.01)

    assert result is True
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2


def test_worker_literal_false_rejection(client):
    """Ensure only a literal False from the handler triggers a fail(), while falsy dicts trigger fulfill()."""
    runtime = WorkerRuntime(client=client, poll_interval=0.1)
    
    # Mock a claimed job payload
    mock_job = MagicMock()
    mock_job.status_code = 200
    mock_job.get.side_effect = lambda k, d=None: {"id": "123", "claim_token": "token", "payload": {}}.get(k, d)
    
    # Test 1: Handler returns literal False (should trigger fail)
    # Using KeyboardInterrupt to bypass the worker's generic 'except Exception' safety net
    with patch.object(client, "claim", side_effect=[mock_job, KeyboardInterrupt()]):
        with patch.object(client, "fail") as mock_fail:
            with patch.object(client, "fulfill") as mock_fulfill:
                try:
                    runtime.listen("test_goal", lambda p: False)
                except KeyboardInterrupt:
                    pass
                assert mock_fail.call_count == 1
                assert mock_fulfill.call_count == 0

    # Test 2: Handler returns falsy dict (should trigger fulfill)
    with patch.object(client, "claim", side_effect=[mock_job, KeyboardInterrupt()]):
        with patch.object(client, "fail") as mock_fail:
            with patch.object(client, "fulfill") as mock_fulfill:
                try:
                    runtime.listen("test_goal", lambda p: {})
                except KeyboardInterrupt:
                    pass
                assert mock_fail.call_count == 0
                assert mock_fulfill.call_count == 1
