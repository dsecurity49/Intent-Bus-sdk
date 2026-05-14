import os
import math
import pytest
import requests
from unittest.mock import patch, MagicMock
from intent_bus import IntentClient
from intent_bus.exceptions import (
    IntentBusAuthError, 
    IntentBusRateLimitError, 
    IntentBusError,
    IntentBusNetworkError
)

@pytest.fixture
def client():
    return IntentClient(api_key="test_key")

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("INTENT_API_KEY", raising=False)
    with patch("os.path.exists", return_value=False):
        with pytest.raises(IntentBusAuthError, match="No API key found"):
            IntentClient()

def test_publish_success(client):
    mock_res = MagicMock()
    mock_res.status_code = 201
    # V2.0: publish() returns IntentStatus, so mock must have valid core fields
    mock_res.json.return_value = {"id": "abc123", "status": "published", "goal": "test_goal"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        result = client.publish("test_goal", {"key": "value"}, namespace="custom")
        
        # V2.0: Result is an object, not a dict
        assert result.id == "abc123"

        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"namespace":"custom"' in sent_body

def test_claim_204_no_content(client):
    """V2.0: claim() returns a ClaimResponse object even on 204."""
    mock_res = MagicMock()
    mock_res.status_code = 204
    mock_res.headers = {"Retry-After": "15"}

    with patch("requests.Session.request", return_value=mock_res):
        result = client.claim(goal="test_goal")

        # V2.0 Object checks
        assert not result  # bool() resolves to False because data is None
        assert result.status_code == 204
        assert result.retry_after == 15.0

def test_claim_routing_headers(client):
    """Ensure worker-id and capabilities are passed in headers."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "job1", "goal": "test_goal", "payload": {}}

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

def test_auth_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 401
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusAuthError):
            client.publish("goal", {})

def test_rate_limit_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 429
    with patch("requests.Session.request", return_value=mock_res):
        with pytest.raises(IntentBusRateLimitError):
            client.publish("goal", {})

def test_network_retry(client):
    """V2.0 explicitly isolates network errors and tests retry counts."""
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

def test_fulfill_with_payload(client):
    """Test that fulfill correctly formats the payload."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"status": "ok"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        # V2.0: pass dictionaries to result, no arbitrary kwargs allowed
        client.fulfill("job123", result={"status": "success", "code": 200})

        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"code":200' in sent_body
        assert '"status":"success"' in sent_body
        assert '"result_type":"json"' in sent_body

def test_canonical_path_query_sorting(client):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "job1", "goal": "test_goal", "payload": {}}
    mock_res.headers = {}  # Silences the protocol mismatch warning in logs

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.claim(goal="test_goal")
        
        # requests.Session.request takes (method, url, **kwargs)
        args, kwargs = mock_req.call_args
        
        # URL is the second positional argument (args[1])
        assert "goal=test_goal&namespace=default" in args[1]

def test_unserializable_payload(client):
    """V2.0 strict JSON testing."""
    class Unserializable: pass
    
    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad": Unserializable()})
        
    # V2.0 Nan-Guard Test
    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad": math.nan})
