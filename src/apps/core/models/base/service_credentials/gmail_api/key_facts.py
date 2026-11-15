"""The public facts of an installed service-account key, and the patterns they must match."""

import re

# The public facts of an installed service-account key, as Google writes them in the key file.
# client_email: "<account>@<project>.iam.gserviceaccount.com" (account and project ids: 6-30 characters).
SERVICE_ACCOUNT_EMAIL_RE = re.compile(
    r"[a-z][a-z0-9-]{4,28}[a-z0-9]@(?P<project>[a-z][a-z0-9-]{4,28}[a-z0-9])\.iam\.gserviceaccount\.com"
)
PROJECT_ID_RE = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
# The numeric OAuth client id the Workspace admin authorizes for domain-wide delegation.
CLIENT_ID_RE = re.compile(r"[0-9]{1,32}")
# private_key_id: 40 lower-case hex characters in every key file Google documents.
KEY_ID_RE = re.compile(r"[0-9a-f]{40}")
# Secrets Manager VersionId bounds (the credential store's version tokens are UUIDs).
VERSION_ID_RE = re.compile(r"[A-Za-z0-9-]{32,64}")
