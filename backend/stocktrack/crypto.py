"""Fernet-based encryption helpers for secrets stored in the DB."""
import base64
import hashlib
from cryptography.fernet import Fernet

def _fernet(secret_key: str) -> Fernet:
    """Derive a 32-byte Fernet key from the app secret."""
    raw = hashlib.sha256(secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)

def encrypt(value: str, secret_key: str) -> str:
    """Encrypt a plaintext string; returns a URL-safe base64 token."""
    return _fernet(secret_key).encrypt(value.encode()).decode()

def decrypt(token: str, secret_key: str) -> str:
    """Decrypt a token produced by encrypt()."""
    return _fernet(secret_key).decrypt(token.encode()).decode()
