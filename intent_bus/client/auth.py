'''Authentication and signature generation helpers.'''
import os
import json
import hmac
import hashlib
from typing import Any, Optional
from ..exceptions import IntentBusAuthError, IntentBusError

def resolve_api_key(api_key: Optional[str] = None) -> str:
    if api_key: return api_key
    
    key = os.environ.get('INTENT_API_KEY')
    if key: return key
    
    key_path = os.path.expanduser('~/.apikey')
    if os.path.exists(key_path):
        try:
            with open(key_path, 'r') as f:
                key = f.read().strip()
                if key: return key
        except Exception: pass
        
    raise IntentBusAuthError('No API key found. Pass api_key, set INTENT_API_KEY env var, or create ~/.apikey')

def canonical_body(payload: Any) -> bytes:
    if payload is None: return b""
    try:
        # allow_nan=False ensures strict JSON standard compliance
        return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as e:
        raise IntentBusError(f"Payload serialization failed: {e}")

def generate_signature(api_key: str, method: str, path: str, timestamp: str, nonce: str, body_bytes: bytes) -> str:
    msg = b"\n".join([
        method.upper().encode(),
        path.encode(),
        timestamp.encode(),
        nonce.encode(),
        body_bytes
    ])
    return hmac.new(api_key.encode(), msg, hashlib.sha256).hexdigest()
