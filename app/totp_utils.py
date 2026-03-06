"""
TOTP (Time-based One-Time Password) utilities for 2FA.
Uses pyotp for TOTP generation/verification and qrcode for QR image generation.
Backup codes are single-use and stored as scrypt hashes in JSON.
"""
import pyotp
import qrcode
import io
import base64
import json
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

from .crypto_utils import encrypt_password, decrypt_password

ISSUER_NAME = "PyCashFlow"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8  # hex chars -> 32-bit entropy each


def generate_totp_secret() -> str:
    """Generate a new random base32 TOTP secret."""
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    """Encrypt a TOTP secret for database storage."""
    return encrypt_password(secret)


def decrypt_totp_secret(encrypted: str) -> str:
    """Decrypt a stored TOTP secret."""
    return decrypt_password(encrypted)


def get_totp_uri(secret: str, email: str) -> str:
    """Build the otpauth:// URI for QR code generation."""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name=ISSUER_NAME,
    )


def generate_qr_code_b64(secret: str, email: str) -> str:
    """Return a base64-encoded PNG of the TOTP QR code."""
    uri = get_totp_uri(secret, email)
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    """
    Verify a TOTP code against the given secret.
    Allows a ±1 window (30 s before/after) to account for clock skew.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)


# ---------------------------------------------------------------------------
# Backup codes
# ---------------------------------------------------------------------------

def generate_backup_codes() -> list[str]:
    """Generate BACKUP_CODE_COUNT random plaintext backup codes."""
    return [secrets.token_hex(BACKUP_CODE_LENGTH // 2) for _ in range(BACKUP_CODE_COUNT)]


def hash_backup_codes(codes: list[str]) -> str:
    """Hash each backup code with scrypt and return a JSON string."""
    hashed = [generate_password_hash(c, method='scrypt') for c in codes]
    return json.dumps(hashed)


def verify_and_consume_backup_code(user, code: str) -> bool:
    """
    Check the submitted code against the user's stored backup codes.
    If a match is found, remove that code from the list (single-use) and
    persist the updated list.  Returns True on success.
    """
    from app import db  # local import to avoid circular deps

    if not user.twofa_backup_codes:
        return False

    try:
        hashed_list: list[str] = json.loads(user.twofa_backup_codes)
    except (json.JSONDecodeError, TypeError):
        return False

    code = code.strip().lower()
    for idx, hashed in enumerate(hashed_list):
        if check_password_hash(hashed, code):
            # Consume the code – remove it so it can't be reused
            hashed_list.pop(idx)
            user.twofa_backup_codes = json.dumps(hashed_list)
            db.session.commit()
            return True

    return False
