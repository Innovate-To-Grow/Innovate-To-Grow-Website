"""Whether the Gmail API provider can send right now: its key, its subjects, and the access check."""

from .key_facts import CLIENT_ID_RE, KEY_ID_RE, SERVICE_ACCOUNT_EMAIL_RE, VERSION_ID_RE
from .subjects import normalize_subject

# Also shown on Email Sending Method, so it names the page the button is on rather than "this page".
RUN_THE_CHECK = (
    "an admin with the Core app runs the access check (Run access check on the Gmail API configuration's page, or "
    "manage.py verify_gmail_access from a shell)"
)


class GmailApiProviderStatusMixin:
    """Key, subject and readiness properties for ``GmailApiProviderConfig``."""

    @property
    def key_configured(self) -> bool:
        """A pinned stored key and well-formed public facts. Nothing here reads the key."""
        account = SERVICE_ACCOUNT_EMAIL_RE.fullmatch(self.service_account_email or "")
        return bool(
            self.key_secret_ref
            and VERSION_ID_RE.fullmatch(self.key_version_id or "")
            and account
            and account.group("project") == self.project_id
            and CLIENT_ID_RE.fullmatch(self.client_id or "")
            and KEY_ID_RE.fullmatch(self.key_id or "")
        )

    @property
    def is_configured(self) -> bool:
        return bool(not self._state.adding and self.is_active and self.key_configured and self.subjects.exists())

    def allows(self, address: str) -> bool:
        """Whether *address* is on the subject allow-list (the only accounts the site impersonates)."""
        if not address or self._state.adding:
            return False
        return self.subjects.filter(subject=normalize_subject(address)).exists()

    def sending_ready(self, from_email: str) -> bool:
        """Configured, and the From address is on the allow-list (the site always sends From the subject)."""
        return self.is_configured and self.allows(from_email)

    @property
    def access_check_current(self) -> bool:
        """The access check passed after the installed key was installed."""
        return bool(
            self.key_installed_at and self.access_checked_at and self.access_checked_at >= self.key_installed_at
        )

    def subject_verified(self, address: str) -> bool:
        """Google issued a gmail.send token for *address* with the installed key (the access check)."""
        if not self.key_installed_at or self._state.adding:
            return False
        subject = self.subjects.filter(subject=normalize_subject(address)).first()
        return bool(subject and subject.verified_at and subject.verified_at >= self.key_installed_at)

    def activation_problem(self, from_email: str) -> str:
        """Why email may not switch to the Gmail API with *from_email* as the From address yet, or ""."""
        if not self.sending_ready(from_email):
            return "the configuration is not active with an installed key and the From address on its allow-list."
        if not self.access_check_current:
            return f"no access check has passed for the installed key; {RUN_THE_CHECK}."
        if not self.subject_verified(from_email):
            return f"the access check has not verified the From address with the installed key; {RUN_THE_CHECK}."
        return ""
