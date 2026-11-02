"""Read and check the service-account key file an admin pastes or uploads, entirely in memory.

Every failure is a ``KeyInputError`` with fixed text that never contains any part of the input, raised ``from
None`` so no parser exception (or its arguments) travels with it. What is kept is the canonical subset of the file
(``stored_key.PAYLOAD_FIELDS``); ``token_uri`` is checked and dropped, because the site always posts to, and names
as ``aud``, ``https://oauth2.googleapis.com/token``.
"""

import json
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from apps.core.models.base.service_credentials.gmail_api import (
    CLIENT_ID_RE,
    KEY_ID_RE,
    PROJECT_ID_RE,
    SERVICE_ACCOUNT_EMAIL_RE,
)

from ..assertion import SigningKeyError, load_signing_key
from .stored_key import PAYLOAD_FIELDS, SERVICE_ACCOUNT_TYPE

# A key file from the console names the accounts.google.com form, one from gcloud the oauth2.googleapis.com form
# (Google Cloud IAM, "Create and delete service account keys").
TOKEN_URIS = ("https://oauth2.googleapis.com/token", "https://accounts.google.com/o/oauth2/token")
UNIVERSE_DOMAIN = "googleapis.com"

TOO_LARGE = "This is larger than a service-account key file can be."
NOT_TEXT = "The key file must be UTF-8 JSON text."
NOT_JSON = "This is not a JSON key file."
DUPLICATE_FIELD = "The key file names one field twice."
NOT_OBJECT = "The key file must be one JSON object."
NOT_SERVICE_ACCOUNT = 'This is not a service-account key (its "type" must be "service_account").'
MISSING_FIELD = "The key file has no {field}, which Google always writes."
BAD_EMAIL = "client_email is not a service-account address (name@project.iam.gserviceaccount.com)."
DOMAIN_SCOPED = "Domain-scoped Google Cloud projects (domain:project) are not supported; use a dedicated project."
PROJECT_MISMATCH = "client_email belongs to another project than project_id: the file looks mixed up."
BAD_TOKEN_URI = "token_uri is not Google's token endpoint."  # nosec B105 - a validation message
BAD_CLIENT_ID = "client_id must be Google's numeric client ID."
BAD_KEY_ID = "private_key_id must be 40 hexadecimal characters."
BAD_UNIVERSE = f"universe_domain must be {UNIVERSE_DOMAIN}."
_REQUIRED = ("project_id", "private_key_id", "private_key", "client_email", "client_id", "token_uri")


class KeyInputError(ValueError):
    """The key file cannot be used. The message is fixed text."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ParsedKey:
    """A checked key: its public facts, and (never shown) the signing key and the payload to store."""

    client_email: str
    client_id: str
    key_id: str
    project_id: str
    private_key: rsa.RSAPrivateKey = field(repr=False)
    payload: dict = field(repr=False)


def _no_duplicates(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise KeyInputError(DUPLICATE_FIELD)
        data[key] = value
    return data


def _no_constants(_name):
    raise KeyInputError(NOT_JSON)


@sensitive_variables()
def _load_json(data) -> dict:
    if isinstance(data, str):
        data = data.encode("utf-8")
    raw = bytes(data or b"")
    if len(raw) > settings.GMAIL_API["key_max_input_bytes"]:
        raise KeyInputError(TOO_LARGE)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise KeyInputError(NOT_TEXT) from None
    try:
        loaded = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except KeyInputError:
        raise
    except (ValueError, RecursionError):
        raise KeyInputError(NOT_JSON) from None
    if not isinstance(loaded, dict):
        raise KeyInputError(NOT_OBJECT)
    return loaded


def _check_identity(values: dict) -> None:
    project_id = values["project_id"]
    if ":" in project_id:
        raise KeyInputError(DOMAIN_SCOPED)
    account = SERVICE_ACCOUNT_EMAIL_RE.fullmatch(values["client_email"])
    if not account or not PROJECT_ID_RE.fullmatch(project_id):
        raise KeyInputError(BAD_EMAIL)
    if account.group("project") != project_id:
        raise KeyInputError(PROJECT_MISMATCH)
    if values["token_uri"] not in TOKEN_URIS:
        raise KeyInputError(BAD_TOKEN_URI)
    if not CLIENT_ID_RE.fullmatch(values["client_id"]):
        raise KeyInputError(BAD_CLIENT_ID)
    if not KEY_ID_RE.fullmatch(values["private_key_id"]):
        raise KeyInputError(BAD_KEY_ID)


@sensitive_variables()
def parse_key(data) -> ParsedKey:
    """The checked key from the pasted text or the uploaded file's bytes."""
    loaded = _load_json(data)
    if loaded.get("type") != SERVICE_ACCOUNT_TYPE:
        raise KeyInputError(NOT_SERVICE_ACCOUNT)
    for name in _REQUIRED:
        if not isinstance(loaded.get(name), str) or not loaded[name]:
            raise KeyInputError(MISSING_FIELD.format(field=name))
    if "universe_domain" in loaded and loaded["universe_domain"] != UNIVERSE_DOMAIN:
        raise KeyInputError(BAD_UNIVERSE)
    _check_identity(loaded)
    try:
        private_key = load_signing_key(loaded["private_key"])
    except SigningKeyError as exc:
        error = KeyInputError(str(exc))
    else:
        payload = {name: loaded[name] for name in PAYLOAD_FIELDS}
        return ParsedKey(
            client_email=loaded["client_email"],
            client_id=loaded["client_id"],
            key_id=loaded["private_key_id"],
            project_id=loaded["project_id"],
            private_key=private_key,
            payload=payload,
        )
    raise error
