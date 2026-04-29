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

    with patch("requests.request", return_value=mock_res) as mock_req:
        result = client.publish("test_goal", {"key": "value"})
        assert result["id"] == "abc123"
        mock_req.assert_called_once()

def test_claim_empty_queue(client):
    mock_res = MagicMock()
    mock_res.status_code = 204

    with patch("requests.request", return_value=mock_res):
        result = client.claim(goal="test_goal")
        assert result is None

def test_auth_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 401

    with patch("requests.request", return_value=mock_res):
        with pytest.raises(IntentBusAuthError):
            client.publish("goal", {})

def test_rate_limit_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 429

    with patch("requests.request", return_value=mock_res):
        with pytest.raises(IntentBusRateLimitError):
            client.publish("goal", {})

def test_network_retry(client):
    with patch("requests.request", side_effect=requests.RequestException("Network Error")) as mock_req:
        with pytest.raises(IntentBusError, match="Network error"):
            client.claim("test_goal")
        assert mock_req.call_count == 3
