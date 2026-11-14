"""Auth security services: RSA key management and Fernet key encryption."""

from .decryption import RSADecryptionError, decrypt_password, is_encrypted_password
from .key_encryption import decrypt_pem, encrypt_pem, is_encrypted
from .rsa_manager import (
    AUTH_KEY_NAME,
    get_or_create_auth_keypair,
    get_public_key_pem,
    purge_retired_auth_keypairs,
    rotate_auth_keypair,
)

__all__ = [
    "AUTH_KEY_NAME",
    "RSADecryptionError",
    "decrypt_password",
    "decrypt_pem",
    "encrypt_pem",
    "get_or_create_auth_keypair",
    "get_public_key_pem",
    "is_encrypted",
    "is_encrypted_password",
    "purge_retired_auth_keypairs",
    "rotate_auth_keypair",
]
