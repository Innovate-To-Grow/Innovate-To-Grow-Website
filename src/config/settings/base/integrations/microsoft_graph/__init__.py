"""
Microsoft Graph: what an installed certificate must satisfy, and the access check that proves the approval holds.

The certificate's private key lives in the credential store (``CREDENTIAL_STORE_SECRETS``); these values only
bound what the Django admin accepts, how long it waits for Microsoft Entra while testing a certificate, when the
site starts warning about expiry, and what ``verify_graph_access`` (and the admin's "Run access check") accepts
as evidence before email delivery may switch to Microsoft Graph.
"""

# Microsoft Entra requires RSA keys of at least 2048 bits for certificate credentials.
GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS = 2048
# Upper bound for one uploaded or pasted certificate, private key or .p12/.pfx bundle.
GRAPH_CERTIFICATE_MAX_INPUT_BYTES = 65536
# A certificate whose validity starts up to this far in the future still counts as valid (laptop clock skew).
GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS = 300
# Timeout of the token request that tests a certificate against Entra before it is installed or rolled back to.
GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS = 10
# The admin's expiry badge turns amber this many days before the current certificate expires...
GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS = 60
# ...and red this many days before (renewal needs OIT to register the new certificate first). From then on
# ``verify_service_configs --strict`` fails while Graph is the selected provider; from the warning threshold on, the
# background worker's hourly maintenance logs a fixed WARNING line.
GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS = 14

# Application permissions (the access token's ``roles``) that InfoSec approved for the Entra app.
# The access check fails when the token carries any other role, unless the Graph config records the reference of
# an InfoSec review that approves it.
GRAPH_APPROVED_APPLICATION_ROLES = ("Mail.Send", "Mail.Read")
# Timeout of each request the access check makes (the token request included).
GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS = 10
# How much of the newest message's raw MIME the access check reads to prove that ``$value`` works; it is discarded.
GRAPH_ACCESS_CHECK_MIME_MAX_BYTES = 4096
# Go-live gate (on in production): switching email delivery to Microsoft Graph needs a complete, passing access
# check for the current certificate, run against the designated deny mailbox...
GRAPH_REQUIRE_ACCESS_EVIDENCE = False
# ...and no older than this many days.
GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS = 30
