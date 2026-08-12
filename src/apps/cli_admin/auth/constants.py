from datetime import timedelta

# Public client id for the i2g-admin CLI (a public OAuth client — no secret).
CLI_CLIENT_ID = "i2g-admin-cli"

# Only S256 PKCE is accepted; "plain" is refused at authorize and token time.
PKCE_METHOD = "S256"

# Authorization codes are single-use and very short-lived.
AUTH_CODE_TTL = timedelta(seconds=60)

# A work-session access token. There is no refresh token; re-login on expiry.
ACCESS_TOKEN_TTL = timedelta(hours=8)

# Belt-and-suspenders denylist on top of the shared safe-ORM denylist. The CLI's
# own tables plus other auth-sensitive tables are never reachable via /admin-api/.
# (cliaccesstoken / impersonationtoken / loginlinktoken already match the shared
# "token" name-part rule, but they are listed here explicitly for clarity.)
CLI_EXTRA_DENIED_MODEL_LABELS = frozenset(
    {
        "cli_admin.cliauthorizationcode",
        "cli_admin.cliaccesstoken",
        "cli_admin.cliauditlog",
        "authn.impersonationtoken",
        "authn.admininvitation",
        "mail.loginlinktoken",
    }
)

# The whole custom auth app is off-limits to the CLI (read AND write). The shared
# denylist only blocks Django's stock "auth" app, not "authn" (Member, ContactEmail,
# RSAKeypair, EmailAuthChallenge, ...). Because /admin-api/ has no per-model permission
# check, a writable identity model is an account-takeover / privilege-escalation vector
# (e.g. re-pointing a verified ContactEmail, flipping Member.is_active). Manage identity
# and auth records through the Django admin UI instead.
CLI_EXTRA_DENIED_APP_LABELS = frozenset({"authn"})

# RFC 8252 §7.3/§8.3: loopback redirect must be a literal loopback IP (never the
# "localhost" DNS name) on the http scheme, with a fixed callback path.
LOOPBACK_REDIRECT_HOSTS = frozenset({"127.0.0.1", "::1"})
LOOPBACK_REDIRECT_PATH = "/callback"
