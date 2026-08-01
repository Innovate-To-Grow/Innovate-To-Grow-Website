import re

DIGITS_ONLY = re.compile(r"^\d+$")
# Compatibility context for event-registration clients that predate event_slug
# and challenge_id. It is accepted only by event registration and remains
# member/phone-bound and single-use. Remove no earlier than 2026-10-23.
LEGACY_EVENT_REGISTRATION_CONTEXT = "event-registration:legacy-phone-only-v1"


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
    # US-only: AWS SNS only delivers to US numbers, which are always 10 national digits.
    return None if len(digits) == 10 else "US phone numbers must be exactly 10 digits."
