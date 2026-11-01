"""
Gmail API (Google Workspace) email provider: what one request may carry and how long it may take, how long tokens
and signed assertions live, and what the Django admin accepts as a service-account key.

The service-account key itself lives in the credential store (``CREDENTIAL_STORE_SECRETS``), never here or in the
database. How fast the site sends and its daily limits are ``DELIVERY_RATES["channels"]["gmail_api_send"]``.

A deployment changes any value with the ``GMAIL_API_OVERRIDES`` environment variable, a JSON object of existing
keys, for example ``GMAIL_API_OVERRIDES='{"request_timeout_seconds": 20}'``. The result is validated here at
import: a bad value raises ``ImproperlyConfigured`` before the site starts.
"""

import os

from .validation import OVERRIDES_ENV, load_gmail_api

__all__ = ["GMAIL_API"]

# Sources, cited by name in the comments below.
# Gmail API messages.send (the media upload endpoint) and its discovery document's mediaUpload.maxSize.
_SEND = "https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send"
# Gmail API usage limits: "there's also a limit of 500 recipients per email message".
_QUOTA = "https://developers.google.com/workspace/gmail/api/reference/quota"
# Google Workspace sending limits: recipients per message and the attachment size limits.
_SENDING_LIMITS = "https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace"
# Google OAuth 2.0 for service accounts: the JWT assertion ("exp" at most 1 hour after "iat") and the token answer.
_SERVICE_ACCOUNT = "https://developers.google.com/identity/protocols/oauth2/service-account"
# Google Cloud IAM: service-account keys ("The default ... is a 2,048-bit RSA key").
_KEYS = "https://docs.cloud.google.com/iam/docs/keys-create-delete"

DEFAULTS = {
    # App default: timeout of each token and send request. It only ends a stuck call: a sign-in code without a
    # cached token needs both, so the worst case (30 s) exceeds DELIVERY_RATES waits.inline_request_budget_seconds,
    # which sizes the normal path (see the note there).
    "request_timeout_seconds": 15,
    # App default: most of a token or send answer the site reads (a Message resource or an error is far smaller).
    "max_response_bytes": 64 * 1024,
    # _QUOTA and _SENDING_LIMITS ("Recipients per message sent with the Gmail API"): 500. Seed and ceiling of the
    # config's "Max recipients per message".
    "max_recipients_per_message": 500,
    # _SENDING_LIMITS: 25 MB of message content and attachments "before encoding" for Business and Education. The
    # site checks the encoded MIME size, which is stricter. Seed and ceiling of the config's "Max message size".
    "max_message_bytes": 25_000_000,
    # _SEND: the upload endpoint's mediaUpload.maxSize (36,700,160 bytes), a protocol ceiling for the value above.
    "upload_max_bytes": 36_700_160,
    # _SERVICE_ACCOUNT allows at most 3,600 s; each assertion is used once right away, so it is kept short.
    "assertion_lifetime_seconds": 300,
    # _SERVICE_ACCOUNT's token answer says expires_in 3600: a longer "expires_in" is not believed...
    "token_max_lifetime_seconds": 3_600,
    # ...and a token is reused until this many seconds before it expires (half its lifetime when that is shorter).
    "token_expiry_margin_seconds": 300,
    # App default: upper bound for one pasted or uploaded service-account key file (a real one is about 2.3 KB).
    "key_max_input_bytes": 16 * 1024,
    # _KEYS: Google creates 2,048-bit RSA keys by default; anything smaller is refused.
    "min_rsa_key_bits": 2_048,
    # App default: timeout of the token request that tests a key before it is installed.
    "key_check_timeout_seconds": 10,
    # App default: timeout of each request the access check makes.
    "access_check_timeout_seconds": 10,
}

GMAIL_API = load_gmail_api(DEFAULTS, os.environ.get(OVERRIDES_ENV, ""))
