from .version import __version__

# --- Safe imports (protect top-level import) ---
try:
    from .client import IntentClient
except Exception as e:
    raise ImportError(f"Failed to import IntentClient: {e}")

try:
    from .exceptions import (
        IntentBusError,
        IntentBusAuthError,
        IntentBusRateLimitError,
    )
except Exception as e:
    raise ImportError(f"Failed to import exceptions: {e}")

__all__ = [
    "IntentClient",
    "IntentBusError",
    "IntentBusAuthError",
    "IntentBusRateLimitError",
    "__version__",
]
