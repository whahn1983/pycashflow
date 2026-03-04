"""
Encryption utilities for securing email passwords stored in the database.
Uses Fernet symmetric encryption derived from the APP_SECRET environment variable.
"""
import os
import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """Derive a Fernet instance from the APP_SECRET environment variable."""
    secret = os.environ.get('APP_SECRET', '')
    if not secret:
        raise ValueError("APP_SECRET environment variable is not set. Cannot encrypt/decrypt passwords.")
    # Derive a 32-byte key from the secret string using SHA-256
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_password(plaintext: str) -> str:
    """
    Encrypt a plaintext password using APP_SECRET.
    Returns the encrypted token as a string for database storage.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    """
    Decrypt a stored encrypted password using APP_SECRET.
    Returns the plaintext password string.
    Raises InvalidToken if the ciphertext is invalid or APP_SECRET has changed.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
