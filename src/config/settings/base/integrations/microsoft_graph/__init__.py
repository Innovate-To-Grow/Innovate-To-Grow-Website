"""
Microsoft Graph certificate credential: what an installed certificate must satisfy.

The certificate's private key lives in the credential store (``CREDENTIAL_STORE_SECRETS``); these values only
bound what the Django admin accepts, how long it waits for Microsoft Entra while testing a certificate, and when
the admin's certificate panel starts warning about expiry.
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
# ...and red this many days before (renewal needs OIT to register the new certificate first).
GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS = 14
