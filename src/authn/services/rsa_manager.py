"""
RSA Key Management Service.

Manages RSA keypairs for authentication encryption with automatic daily rotation.
"""

import base64
from datetime import timedelta

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.utils import timezone

from authn.models import RSAKeypair

# Key name for authentication encryption
AUTH_KEY_NAME = "auth-encryption"

# Key rotation interval (1 day)
KEY_ROTATION_INTERVAL = timedelta(days=1)


class RSADecryptionError(Exception):
    """Raised when RSA decryption fails."""

    pass


def get_or_create_auth_keypair() -> RSAKeypair:
    """
    Get the active authentication keypair, creating one if it doesn't exist.
    Automatically rotates the key if it's older than KEY_ROTATION_INTERVAL.
    """
    keypair = RSAKeypair.objects.filter(name=AUTH_KEY_NAME, is_active=True).first()

    if keypair is None:
        # Create a new keypair
        keypair = RSAKeypair.objects.create(name=AUTH_KEY_NAME, is_active=True)
        return keypair

    # Check if rotation is needed
    last_rotation = keypair.rotated_at or keypair.created_at
    if timezone.now() - last_rotation > KEY_ROTATION_INTERVAL:
        rotate_auth_keypair(keypair)

    return keypair


def rotate_auth_keypair(keypair: RSAKeypair | None = None) -> RSAKeypair:
    """
    Rotate the authentication keypair with new keys.
    """
    if keypair is None:
        keypair = get_or_create_auth_keypair()

    public_pem, private_pem = RSAKeypair.generate_keypair()
    keypair.rotate(public_pem, private_pem)
    return keypair


def get_public_key_pem() -> tuple[str, str]:
    """
    Get the current public key PEM and key_id for authentication encryption.
    Returns (public_key_pem, key_id).
    """
    keypair = get_or_create_auth_keypair()
    return keypair.public_key_pem, str(keypair.key_id)


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
        # Get the keypair
        if key_id:
            keypair = RSAKeypair.objects.filter(key_id=key_id).first()
            if not keypair:
                # Fall back to active keypair
                keypair = get_or_create_auth_keypair()
        else:
            keypair = get_or_create_auth_keypair()

        # Load private key
        private_key = serialization.load_pem_private_key(
            keypair.private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )

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
    except Exception:
        return False
