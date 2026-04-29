import pytest
from unittest.mock import patch, MagicMock
from intent_bus import IntentClient
from intent_bus.exceptions import IntentBusAuthError, IntentBusRateLimitError

@pytest.fixture
def client():
    return IntentClient(host="https://example.com", api_key="test_key")

def test_publish_success(client):
    mock_res = MagicMock()
    mock_res.status_code = 201
    mock_res.json.return_value = {"id": "abc123", "status": "published"}

    with patch("requests.post", return_value=mock_res):
        result = client.publish("test_goal", {"key": "value"})
        assert result["id"] == "abc123"

def test_claim_empty_queue(client):
    mock_res = MagicMock()
    mock_res.status_code = 204

    with patch("requests.post", return_value=mock_res):
        result = client.claim(goal="test_goal")
        assert result is None

def test_auth_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 401

    with patch("requests.post", return_value=mock_res):
        with pytest.raises(IntentBusAuthError):
            client.publish("goal", {})

def test_rate_limit_error(client):
    mock_res = MagicMock()
    mock_res.status_code = 429

    with patch("requests.post", return_value=mock_res):
        with pytest.raises(IntentBusRateLimitError):
            client.publish("goal", {})
