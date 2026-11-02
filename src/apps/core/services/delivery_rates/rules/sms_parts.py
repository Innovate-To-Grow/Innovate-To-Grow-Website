"""How many message parts an SMS body takes, which is what an origination number's MPS limit counts.

GSM 03.38 (3GPP TS 23.038): a body made only of GSM-7 characters fits 160 septets in one message, or 153 per part
once it is split (a 7-septet user data header joins the parts); an extension character takes two septets (escape +
character) and is never split across parts. Any other character makes the whole body UCS-2: 70 UTF-16 code units in
one message, or 67 per part, and a character outside the Basic Multilingual Plane is a surrogate pair of two code
units that is never split either. These sizes are the encoding's definition, not tunables.
"""

GSM_SINGLE = 160
GSM_PART = 153
UCS2_SINGLE = 70
UCS2_PART = 67

# The GSM 7-bit default alphabet (the escape character 0x1B is left out: it only introduces the extension table).
GSM_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
# The default extension table: each takes two septets.
GSM_EXTENSION = frozenset("\f^{}\\[~]|€")


def _gsm_sizes(body: str) -> list[int] | None:
    sizes = []
    for char in body:
        if char in GSM_BASIC:
            sizes.append(1)
        elif char in GSM_EXTENSION:
            sizes.append(2)
        else:
            return None
    return sizes


def _ucs2_sizes(body: str) -> list[int]:
    return [2 if ord(char) > 0xFFFF else 1 for char in body]


def _parts(sizes: list[int], single: int, part: int) -> int:
    if sum(sizes) <= single:
        return 1
    count, used = 1, 0
    for size in sizes:
        if used + size > part:
            count, used = count + 1, 0
        used += size
    return count


def sms_parts(body: str) -> int:
    """The number of parts ``body`` is sent as (at least 1: an empty SMS is still one message)."""
    text = str(body or "")
    gsm = _gsm_sizes(text)
    if gsm is not None:
        return _parts(gsm, GSM_SINGLE, GSM_PART)
    return _parts(_ucs2_sizes(text), UCS2_SINGLE, UCS2_PART)


def sms_encoding(body: str) -> str:
    """The body's encoding, "GSM-7" or "UCS-2", for the admin's send estimate."""
    return "GSM-7" if _gsm_sizes(str(body or "")) is not None else "UCS-2"
