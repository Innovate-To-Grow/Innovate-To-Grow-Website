"""
Credential key store: where the site keeps the private keys it signs with.

The database holds only public data and a pointer (the secret's ARN and a pinned
version id); the key itself lives in the store selected here
(``apps.core.services.credential_store``):

  local_file     – 0700 directory / 0600 files under the gitignored ``src/data/`` (development, throwaway keys).
  memory         – process memory (tests).
  secretsmanager – AWS Secrets Manager through the ECS task role (production).

Production sets the backend to Secrets Manager and turns on the require flag; the
``core`` system check then refuses to start with any other backend.
"""

from ...framework.environment import BASE_DIR

CREDENTIAL_STORE_BACKEND = "local_file"
CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER = False
CREDENTIAL_STORE_LOCAL_DIR = BASE_DIR / "data" / "credential-store"

# Logical name -> Secrets Manager secret name. Each secret is created empty by aws/cicd/identity-stack.json, and
# none may sit in the itg/backend/aws-credentials/ namespace that the AWS credential resolver reads.
CREDENTIAL_STORE_SECRETS = {
    "microsoft_graph_certificate_key": "itg/backend/microsoft-graph/certificate-key",
    "gmail_api_service_account_key": "itg/backend/gmail-api/service-account-key",
}

# A new version gets this label instead of AWSCURRENT, so storing a key never changes which version Secrets Manager
# calls current. The database pin decides which version the site signs with.
CREDENTIAL_STORE_STAGED_LABEL = "I2G-STAGED"

CREDENTIAL_STORE_AWS_REGION = "us-west-2"
CREDENTIAL_STORE_AWS_ACCOUNT_ID = "394167325273"
CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS = 3
CREDENTIAL_STORE_READ_TIMEOUT_SECONDS = 5
# Includes the first attempt. A retried write is safe: every write carries a deterministic version token.
CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS = 3
# Secrets Manager's own SecretString limit.
CREDENTIAL_STORE_MAX_PAYLOAD_BYTES = 65536
