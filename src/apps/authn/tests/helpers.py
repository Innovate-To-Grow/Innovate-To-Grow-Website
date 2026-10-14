"""
Test helpers for creating members with ContactEmail records.
"""

import base64
import binascii
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.authn.models import ContactEmail, Member

# A real 1x1 PNG. Profile-image uploads are checked against magic bytes on both the admin and the API
# path (apps.authn.services.members.profile_image), so placeholder payloads like b"new-image" are
# rejected — tests that upload an avatar need actual image bytes.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PNG_1PX_DATA_URI = f"data:image/png;base64,{base64.b64encode(PNG_1PX).decode()}"


def _craft_png_bomb() -> bytes:
    """``PNG_1PX`` with the IHDR declaring 50000x5000 px; the file stays 70 bytes.

    Pillow refuses it with ``DecompressionBombError`` when opening. The IHDR CRC (bytes 29-33,
    over the ``IHDR`` tag plus its 13 data bytes) is recomputed or Pillow rejects the chunk as
    corrupt before ever checking the dimensions.
    """
    bomb = bytearray(PNG_1PX)
    bomb[16:20] = (50000).to_bytes(4, "big")
    bomb[20:24] = (5000).to_bytes(4, "big")
    bomb[29:33] = (binascii.crc32(bytes(bomb[12:29])) & 0xFFFFFFFF).to_bytes(4, "big")
    return bytes(bomb)


PNG_BOMB = _craft_png_bomb()


def png_upload(name="avatar.png"):
    """A valid PNG upload for profile-image tests."""
    return SimpleUploadedFile(name, PNG_1PX, content_type="image/png")


def scrape_admin_form(client, url, overrides=None, submit="_save"):
    """GET an admin change page and return its fields as a POST-ready dict.

    Admin change forms carry management forms, hidden ``initial-*`` inputs and readonly fields that a
    hand-written payload gets wrong (a missing key silently re-renders the form with errors instead of
    saving), so scrape what the page actually rendered.
    """
    from html.parser import HTMLParser

    response = client.get(url)
    fields: dict[str, str] = {}
    state = {"textarea": None, "select": None, "selected": None}

    class _FormParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            name = attr.get("name")
            if tag == "input" and name:
                if attr.get("type") == "checkbox":
                    if "checked" in attr:
                        fields[name] = attr.get("value", "on")
                elif attr.get("type") != "file":
                    fields.setdefault(name, attr.get("value", ""))
            elif tag == "textarea" and name:
                state["textarea"] = name
            elif tag == "select" and name:
                state["select"] = name
            elif tag == "option" and state["select"] and "selected" in attr:
                state["selected"] = attr.get("value", "")

        def handle_data(self, data):
            if state["textarea"]:
                fields.setdefault(state["textarea"], data.strip())

        def handle_endtag(self, tag):
            if tag == "textarea":
                state["textarea"] = None
            elif tag == "select" and state["select"]:
                if state["selected"] is not None:
                    fields.setdefault(state["select"], state["selected"])
                state["select"] = None
                state["selected"] = None

    _FormParser().feed(response.content.decode())

    if overrides:
        fields.update(overrides)
    for key in ("_addanother", "_continue", "_save"):
        fields.pop(key, None)
    if submit:
        fields[submit] = "1"
    return fields


def create_test_member(email, password="testpass123", **kwargs):
    """
    Create a Member with a primary ContactEmail record.
    Member.email is left blank; the email is stored in ContactEmail.
    """
    member = Member.objects.create_user(
        password=password,
        **kwargs,
    )
    ContactEmail.objects.create(
        member=member,
        email_address=email,
        email_type="primary",
        verified=True,
    )
    # Store the email on the instance for convenience in tests
    member._test_email = email
    return member


def malformed_field_bodies(field: str) -> dict[str, str]:
    """Raw JSON request bodies a credential-exchange view must answer with a 400 "missing", not a 500.

    Covers a non-string ``field`` value and a body that is not an object at all.
    """
    return {
        "null value": f'{{"{field}": null}}',
        "numeric value": f'{{"{field}": 123}}',
        "boolean value": f'{{"{field}": true}}',
        "list value": f'{{"{field}": ["a"]}}',
        "object value": f'{{"{field}": {{"a": 1}}}}',
        "null body": "null",
        "list body": '["a"]',
        "string body": '"credential"',
        "numeric body": "123",
    }


MALFORMED_TOKEN_BODIES = malformed_field_bodies("token")
MALFORMED_REFRESH_BODIES = malformed_field_bodies("refresh")

# Token strings that can never be a real credential and that the database layer cannot take: a lone surrogate
# (not UTF-8 encodable, so a 500 in the ORM driver) and NUL (rejected by PostgreSQL). Written as JSON escapes so the
# request body itself stays plain ASCII.
UNUSABLE_TOKEN_BODIES = {
    "lone high surrogate": '{"token": "\\ud800"}',
    "lone low surrogate": '{"token": "\\udfff"}',
    "surrogate inside text": '{"token": "abc\\ud800def"}',
    "NUL": '{"token": "\\u0000"}',
    "NUL inside text": '{"token": "abc\\u0000def"}',
    "NUL after whitespace": '{"token": "  \\u0000  "}',
}


def bearer_header(member) -> str:
    """``Authorization`` value carrying a currently valid access token for ``member``."""
    return f"Bearer {RefreshToken.for_user(member).access_token}"


def expired_bearer_header(member) -> str:
    """``Authorization`` value carrying a correctly signed access token for ``member`` that has expired."""
    access = RefreshToken.for_user(member).access_token
    access.set_exp(from_time=timezone.now() - timedelta(hours=2))  # one-hour lifetime: expired an hour ago
    return f"Bearer {access}"


def access_token_owner_id(access: str) -> str:
    """The member id an access token was issued for."""
    return str(AccessToken(access)[jwt_settings.USER_ID_CLAIM])


def stale_bearer_headers() -> dict[str, str]:
    """``Authorization`` values the SPA can still hold for a session that no longer works.

    The shared axios client attaches whatever access token is in local storage to every request. Each
    value below makes ``JWTAuthentication`` answer 401 on any view that still runs authentication, so a
    credential-exchange view that has not opted out fails before its handler ever runs.
    """
    expired_owner = Member.objects.create_user(password="StrongPass123!", is_active=True)

    deleted = Member.objects.create_user(password="StrongPass123!", is_active=True)
    deleted_header = bearer_header(deleted)
    deleted.delete()

    inactive = Member.objects.create_user(password="StrongPass123!", is_active=False)

    return {
        "expired access token": expired_bearer_header(expired_owner),
        "garbage token": "Bearer not-a-jwt",
        "deleted member": deleted_header,
        "inactive member": bearer_header(inactive),
    }
