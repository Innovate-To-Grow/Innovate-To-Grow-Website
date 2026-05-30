import re
from hashlib import sha256

from django.core.cache import cache

PHONE_VERIFICATION_TTL = 900
DIGITS_ONLY = re.compile(r"^\d+$")


def _normalize_phone(phone: str, region: str) -> str:
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        country_code = region.split("-")[0] if "-" in region else region
        phone = f"+{country_code}{phone}"
    return phone


def _validate_phone_digits(phone: str, region: str) -> str | None:
    digits = phone.strip()
    if not digits:
        return None

    country_code = region.split("-")[0] if "-" in region else region
    if digits.startswith("+"):
        digits = digits[1:]
        if not DIGITS_ONLY.match(digits):
            return "Phone number must contain only digits."
        if digits.startswith(country_code):
            digits = digits[len(country_code) :]
    elif not DIGITS_ONLY.match(digits):
        return "Phone number must contain only digits."

    if not digits:
        return "Phone number is too short (minimum 4 digits)."
    if country_code == "1":
        return None if len(digits) == 10 else "US/Canada phone numbers must be exactly 10 digits."
    if country_code == "86":
        return None if len(digits) == 11 else "China phone numbers must be exactly 11 digits."
    if len(digits) < 4:
        return "Phone number is too short (minimum 4 digits)."
    if len(digits) > 15:
        return "Phone number is too long (maximum 15 digits)."
    return None


def _phone_verification_cache_key(user, phone: str) -> str:
    phone_digest = sha256(phone.encode("utf-8")).hexdigest()
    return f"event:phone-verified:{user.pk}:{phone_digest}"


def _clear_phone_verification(user, phone: str) -> None:
    cache.delete(_phone_verification_cache_key(user, phone))


def _mark_phone_verified(user, phone: str) -> None:
    cache.set(
        _phone_verification_cache_key(user, phone),
        True,
        timeout=PHONE_VERIFICATION_TTL,
    )


def _consume_phone_verification(user, phone: str) -> bool:
    cache_key = _phone_verification_cache_key(user, phone)
    verified = cache.get(cache_key) is True
    if verified:
        cache.delete(cache_key)
    return verified
