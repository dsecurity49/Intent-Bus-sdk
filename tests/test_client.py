import pytest
import os
import requests
from unittest.mock import patch, MagicMock
from intent_bus import IntentClient
from intent_bus.exceptions import IntentBusAuthError, IntentBusRateLimitError, IntentBusError

@pytest.fixture
def client():
    # Uses the default dsecurity server for testing
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
        result = client.publish("test_goal", {"key": "value"})
        assert result["id"] == "abc123"
        mock_req.assert_called_once()

def test_claim_empty_queue(client):
    mock_res = MagicMock()
    mock_res.status_code = 204

    with patch("requests.Session.request", return_value=mock_res):
        result = client.claim(goal="test_goal")
        assert result is None

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
    with patch("requests.Session.request", side_effect=requests.RequestException("Network Error")) as mock_req:
        with pytest.raises(IntentBusError, match="Network error"):
            client.claim("test_goal")
        assert mock_req.call_count == 1  # Claim is state-changing, should NOT retry
        
    with patch("requests.Session.request", side_effect=requests.RequestException("Network Error")) as mock_req:
        with pytest.raises(IntentBusError, match="Network error"):
            client.publish("test_goal", {})
        assert mock_req.call_count == 3  # Publish is idempotent, should retry

def test_request_signing_headers(client):
    mock_res = MagicMock()
    mock_res.status_code = 201
    mock_res.json.return_value = {"id": "123", "status": "published"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.publish("test_goal", {"key": "value"})
        
        mock_req.assert_called_once()
        _, kwargs = mock_req.call_args
        
        headers = kwargs.get("headers", {})
        
        # Assert strict auth headers exist
        assert "X-API-KEY" in headers
        assert headers["X-API-KEY"] == "test_key"
        assert "X-Timestamp" in headers
        assert "X-Nonce" in headers
        assert "X-Signature" in headers
        assert "Idempotency-Key" in headers
        
        # Assert signature is a valid SHA-256 hex digest length (64 chars) and valid hex
        assert len(headers["X-Signature"]) == 64
        assert all(c in "0123456789abcdef" for c in headers["X-Signature"])
        
        # Assert the canonical path was constructed correctly
        assert kwargs["url"].endswith("/intent")

def test_canonical_path_query_sorting(client):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "job1"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        # Pass a goal to trigger the query string logic in claim()
        client.claim(goal="test_goal")
        
        mock_req.assert_called_once()
        _, kwargs = mock_req.call_args
        
        # Ensure the query string is appended correctly for the canonical signature
        assert kwargs["url"].endswith("/claim?goal=test_goal")
        assert "X-Signature" in kwargs.get("headers", {})

def test_unserializable_payload(client):
    class UnserializableObject:
        pass
        
    with pytest.raises(IntentBusError, match="Payload serialization failed"):
        client.publish("test_goal", {"bad_key": UnserializableObject()})

def test_signature_freshness_per_request(client):
    mock_res = MagicMock()
    mock_res.status_code = 201
    mock_res.json.return_value = {"id": "123"}

    with patch("requests.Session.request", return_value=mock_res) as mock_req:
        client.publish("test_goal", {"key": "value"})
        client.publish("test_goal", {"key": "value"})
        
        assert mock_req.call_count == 2
        
        # Extract headers from both calls
        args_1, kwargs_1 = mock_req.call_args_list[0]
        args_2, kwargs_2 = mock_req.call_args_list[1]
        
        headers_1 = kwargs_1.get("headers", {})
        headers_2 = kwargs_2.get("headers", {})
        
        # The signatures MUST be different because of the fresh nonce/timestamp
        assert headers_1["X-Signature"] != headers_2["X-Signature"]
        assert headers_1["X-Nonce"] != headers_2["X-Nonce"]
