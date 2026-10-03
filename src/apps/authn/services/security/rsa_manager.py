"""
RSA Key Management Service.

Manages RSA keypairs for authentication encryption with automatic daily rotation.
"""

import base64
import threading
import time
from collections import OrderedDict
from datetime import timedelta

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.authn.models import RSAKeypair

# Key name for authentication encryption
AUTH_KEY_NAME = "auth-encryption"

# Key rotation interval (1 day)
KEY_ROTATION_INTERVAL = timedelta(days=1)

# Retired private keys stay decryptable for one client compatibility window,
# then remain stored (but unusable) for an additional forensic/rollback window.
KEY_DECRYPTION_GRACE_PERIOD = timedelta(hours=24)
KEY_PURGE_RETENTION = timedelta(hours=48)

# Parsed private keys, reused across decrypts in this process. Parsing a PEM runs the RSA key consistency check,
# about 45 ms for a 2048-bit key: nearly all of a password sign-in that never reaches PBKDF2 (unknown identifier).
# Entries are keyed on the key id plus a SECRET_KEY-keyed fingerprint of the stored (encrypted) key material, so a
# row whose material changes misses. Only the parse is cached: decrypt_password still reads the row and applies the
# active/grace checks on every call, so rotation, retirement and purge take effect immediately. Entries expire after
# a TTL (re-parsed at most that often) so a retired key's parsed form does not outlive its use by much.
_PRIVATE_KEY_CACHE_SIZE = 8
_PRIVATE_KEY_CACHE_TTL_SECONDS = 15 * 60
_PRIVATE_KEY_FINGERPRINT_SALT = "rsa-manager.private-key-cache"
_private_keys: OrderedDict[tuple[str, str], tuple[float, PrivateKeyTypes]] = OrderedDict()
_private_keys_lock = threading.Lock()
_monotonic = time.monotonic


class RSADecryptionError(Exception):
    """Raised when RSA decryption fails."""

    pass


def clear_private_key_cache() -> None:
    """Forget every parsed private key held by this process."""
    with _private_keys_lock:
        _private_keys.clear()


def _load_private_key(keypair: RSAKeypair) -> PrivateKeyTypes:
    """The parsed private key of ``keypair``, reusing an earlier parse of the same stored key material."""
    fingerprint = salted_hmac(_PRIVATE_KEY_FINGERPRINT_SALT, keypair.private_key_pem, algorithm="sha256").hexdigest()
    cache_key = (str(keypair.key_id), fingerprint)
    now = _monotonic()
    with _private_keys_lock:
        for stale in [key for key, (expires, _parsed) in _private_keys.items() if expires <= now]:
            del _private_keys[stale]
        entry = _private_keys.get(cache_key)
        if entry is not None:
            _private_keys.move_to_end(cache_key)
            return entry[1]

    # Parsed outside the lock: two threads missing at once both parse, and either result is correct.
    private_key = serialization.load_pem_private_key(
        keypair.decrypted_private_key_pem.encode("utf-8"),
        password=None,
        backend=default_backend(),
    )

    with _private_keys_lock:
        for replaced in [key for key in _private_keys if key[0] == cache_key[0] and key != cache_key]:
            del _private_keys[replaced]  # the same key id with other material: that material is gone
        _private_keys[cache_key] = (now + _PRIVATE_KEY_CACHE_TTL_SECONDS, private_key)
        _private_keys.move_to_end(cache_key)
        while len(_private_keys) > _PRIVATE_KEY_CACHE_SIZE:
            _private_keys.popitem(last=False)
    return private_key


@transaction.atomic
def get_or_create_auth_keypair() -> RSAKeypair:
    """
    Get the active authentication keypair, creating one if it doesn't exist.
    Automatically rotates the key if it's older than KEY_ROTATION_INTERVAL.
    A database constraint guarantees at most one active row for this key name.
    """
    purge_retired_auth_keypairs()
    keypair = RSAKeypair.objects.select_for_update().filter(name=AUTH_KEY_NAME, is_active=True).first()
    if keypair is None:
        # A partial unique constraint arbitrates concurrent first-key creation.
        # The inner savepoint keeps the outer transaction usable if another
        # request wins the insert.
        try:
            with transaction.atomic():
                keypair = RSAKeypair.objects.create(name=AUTH_KEY_NAME, is_active=True)
        except IntegrityError:
            keypair = RSAKeypair.objects.select_for_update().get(
                name=AUTH_KEY_NAME,
                is_active=True,
            )
        return keypair

    # Check if rotation is needed
    last_rotation = keypair.created_at
    if timezone.now() - last_rotation > KEY_ROTATION_INTERVAL:
        return rotate_auth_keypair(keypair)

    return keypair


def rotate_auth_keypair(keypair: RSAKeypair | None = None) -> RSAKeypair:
    """
    Rotate the authentication keypair into a new row with a new key ID.
    """
    if keypair is None:
        keypair = get_or_create_auth_keypair()

    return keypair.rotate()


def purge_retired_auth_keypairs(*, now=None) -> int:
    """Delete retired authentication keys after the 48-hour retention window."""
    cutoff = (now or timezone.now()) - KEY_PURGE_RETENTION
    stale = RSAKeypair.objects.filter(
        name=AUTH_KEY_NAME,
        is_active=False,
    ).filter(Q(rotated_at__lte=cutoff) | Q(rotated_at__isnull=True, updated_at__lte=cutoff))
    deleted, _ = stale.delete()
    return deleted


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
        now = timezone.now()
        if key_id:
            keypair = RSAKeypair.objects.filter(
                key_id=key_id,
                name=AUTH_KEY_NAME,
            ).first()
            if not keypair:
                raise RSADecryptionError("Unknown RSA key identifier.")
            if not keypair.is_active:
                retired_at = keypair.rotated_at
                if retired_at is None or retired_at <= now - KEY_DECRYPTION_GRACE_PERIOD:
                    raise RSADecryptionError("RSA key identifier has expired.")
        else:
            keypair = get_or_create_auth_keypair()

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
