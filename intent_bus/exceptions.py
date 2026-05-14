class IntentBusError(Exception):
    '''Base exception for all Intent Bus errors.'''
    pass

class IntentBusAuthError(IntentBusError):
    '''Raised when API key is missing, invalid, or signature verification fails.'''
    pass

class IntentBusProtocolError(IntentBusError):
    '''Raised when the server response violates the expected SDK data schema.'''
    pass

class IntentBusRateLimitError(IntentBusError):
    '''Raised when the client is rate-limited by the server (HTTP 429).'''
    pass

class IntentBusNetworkError(IntentBusError):
    '''Raised when requests timeout or connections are dropped after all retries.'''
    pass
