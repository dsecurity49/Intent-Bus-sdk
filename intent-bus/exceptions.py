class IntentBusError(Exception):
    """Base exception for Intent Bus errors."""
    pass

class IntentBusAuthError(IntentBusError):
    """Raised when authentication fails."""
    pass

class IntentBusRateLimitError(IntentBusError):
    """Raised when rate limit is exceeded."""
    pass
