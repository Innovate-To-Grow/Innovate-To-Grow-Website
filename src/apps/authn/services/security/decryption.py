"""Decrypting a password the browser encrypted with the auth public key (RSA-OAEP), with the keypairs still in
their grace period."""

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.utils import timezone

from apps.authn.models import RSAKeypair

from .rsa_manager import AUTH_KEY_NAME, KEY_DECRYPTION_GRACE_PERIOD, _load_private_key, get_or_create_auth_keypair


class RSADecryptionError(Exception):
    """Raised when RSA decryption fails."""

    pass


def _decryption_keypair(key_id: str) -> RSAKeypair:
    """The named key: active, or retired within the decryption grace period."""
    keypair = RSAKeypair.objects.filter(key_id=key_id, name=AUTH_KEY_NAME).first()
    if not keypair:
        raise RSADecryptionError("Unknown RSA key identifier.")
    if not keypair.is_active:
        retired_at = keypair.rotated_at
        if retired_at is None or retired_at <= timezone.now() - KEY_DECRYPTION_GRACE_PERIOD:
            raise RSADecryptionError("RSA key identifier has expired.")
    return keypair


def decrypt_password(encrypted_password_b64: str, key_id: str | None = None) -> str:
    """
    Decrypt a password that was encrypted with the public key.

    Args:
        encrypted_password_b64: Base64-encoded encrypted password
        key_id: Optional key ID to use for decryption (for key rotation handling)

    Returns:
        Decrypted password string

    Raises:
        RSADecryptionError: If decryption fails
    """
    try:
        keypair = _decryption_keypair(key_id) if key_id else get_or_create_auth_keypair()

        # Load private key (decrypted from Fernet-encrypted DB storage; parsed once per stored material)
        private_key = _load_private_key(keypair)

        # Decode the base64 encrypted data
        encrypted_data = base64.b64decode(encrypted_password_b64)

        # Decrypt using OAEP padding
        decrypted = private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        return decrypted.decode("utf-8")

    except Exception as e:
        raise RSADecryptionError(f"Failed to decrypt password: {e}") from e


def is_encrypted_password(password: str) -> bool:
    """
    Check if the password appears to be RSA encrypted (base64 encoded).
    Encrypted passwords are typically 256+ bytes when base64 encoded.
    """
    if not password:
        return False

    # Check if it's valid base64 and has expected length for RSA encrypted data
    try:
        decoded = base64.b64decode(password)
        # RSA 2048-bit encryption produces 256 bytes of ciphertext
        return len(decoded) >= 128
    except (ValueError, TypeError):
        return False
