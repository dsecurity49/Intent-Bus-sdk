import pytest
import os
import requests
from unittest.mock import patch, MagicMock
from intent_bus import IntentClient
from intent_bus.exceptions import IntentBusAuthError, IntentBusRateLimitError, IntentBusError

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
    mock_res.json.return_value = {"id": "abc123", "status": "published"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        # v7.5: namespace is now part of the payload
        result = client.publish("test_goal", {"key": "value"}, namespace="custom")
        assert result["id"] == "abc123"
        
        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"namespace":"custom"' in sent_body

def test_claim_204_no_content(client):
    """v7.5: claim() returns a ClaimResponse object even on 204."""
    mock_res = MagicMock()
    mock_res.status_code = 204
    mock_res.headers = {"Retry-After": "15"}

    with patch("requests.Session.request", return_value=mock_res):
        result = client.claim(goal="test_goal")
        
        # Legacy check: empty dict evaluates to False
        assert not result 
        # Modern check: attributes exist
        assert result.status_code == 204
        assert result.retry_after == 15

def test_claim_v75_routing_headers(client):
    """Ensure worker-id and capabilities are passed in headers."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "job1"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.claim(
            goal="test_goal", 
            worker_id="test-worker", 
            capabilities="test-cap"
        )

        _, kwargs = mock_req.call_args
        headers = kwargs.get("headers", {})
        assert headers["X-Worker-ID"] == "test-worker"
        assert headers["X-Worker-Capabilities"] == "test-cap"

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
    with patch("requests.Session.request", side_effect=requests.RequestException("Net Error")) as mock_req:
        with pytest.raises(IntentBusError):
            client.claim("test_goal")
        assert mock_req.call_count == 1  # Claim (POST) should NOT retry by default

    with patch("requests.Session.request", side_effect=requests.RequestException("Net Error")) as mock_req:
        with pytest.raises(IntentBusError):
            client.publish("test_goal", {})
        assert mock_req.call_count == 3  # Publish is set to retry in SDK

def test_fulfill_with_custom_payload(client):
    """Test that fulfill correctly passes kwargs to server."""
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"status": "ok"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.fulfill("job123", result="success", code=200)
        
        _, kwargs = mock_req.call_args
        sent_body = kwargs["data"].decode("utf-8")
        assert '"code":200' in sent_body
        assert '"result":"success"' in sent_body

def test_canonical_path_query_sorting(client):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "job1"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        # namespace defaults to 'default' in v7.5
        client.claim(goal="test_goal")
        _, kwargs = mock_req.call_args
        # lexicographic order: goal=test_goal&namespace=default
        assert "goal=test_goal&namespace=default" in kwargs["url"]

def test_unserializable_payload(client):
    class Unserializable: pass
    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad": Unserializable()})
