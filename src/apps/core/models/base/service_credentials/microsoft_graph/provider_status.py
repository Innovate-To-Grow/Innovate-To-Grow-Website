"""What a Graph configuration can do right now: its certificates, whether it is configured, and which mailboxes it may
send as."""

from django.utils import timezone

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from .certificate import MicrosoftGraphCertificate
from .mailboxes import MicrosoftGraphMailboxScope, normalize_mailbox


class GraphProviderStatusMixin:
    """Certificate and readiness properties for ``MicrosoftGraphProviderConfig``."""

    @property
    def current_certificate(self):
        """The certificate the site signs with, or None."""
        if self._state.adding:
            return None
        return self.certificates.filter(state=MicrosoftGraphCertificate.State.CURRENT).first()

    @property
    def previous_certificate(self):
        """The certificate the current one replaced, kept for rollback, or None."""
        if self._state.adding:
            return None
        return self.certificates.filter(state=MicrosoftGraphCertificate.State.PREVIOUS).first()

    @property
    def certificate_expires_at(self):
        certificate = self.current_certificate
        return certificate.not_after if certificate is not None else None

    @property
    def certificate_expired(self) -> bool:
        expires_at = self.certificate_expires_at
        return expires_at is not None and expires_at <= timezone.now()

    @property
    def credential_configured(self) -> bool:
        """A current certificate, valid now and tested for this tenant and app, pins a stored private key."""
        certificate = self.current_certificate
        return certificate is not None and certificate.usable_for(self)

    @property
    def is_configured(self):
        """Active, saved, well-formed and scoped, so readiness gates agree with what the Graph services accept."""
        return self._configured()

    def _configured(self, scopes=None) -> bool:
        if self._state.adding or not self.is_active:
            return False
        well_formed = (
            is_entra_tenant(self.tenant_id)
            and is_guid(self.client_id)
            and (not self.mailbox or is_exchange_mailbox(self.mailbox))
        )
        return bool(
            well_formed and self.credential_configured and (self.mailbox_scopes.exists() if scopes is None else scopes)
        )

    def sender_mailbox(self, from_email: str) -> str:
        """The mailbox Graph sends as (and whose inbox the admin reads): the configured one or the From address."""
        return normalize_mailbox(self.mailbox or from_email)

    def allows(self, mailbox: str, permission: str, *, scopes=None) -> bool:
        """Whether *mailbox* is in this config's scope with *permission* (``"send"`` or ``"read"``).

        *scopes* (``{mailbox: permission level}``) stands in for the stored scope, to check a change before it is saved.
        """
        if not mailbox:
            return False
        if scopes is not None:
            return MicrosoftGraphMailboxScope.level_grants(scopes.get(normalize_mailbox(mailbox)), permission)
        if self._state.adding:
            return False
        scope = self.mailbox_scopes.filter(mailbox=normalize_mailbox(mailbox)).first()
        return scope is not None and scope.grants(permission)

    def sending_ready(self, from_email: str, *, scopes=None) -> bool:
        """Configured, and both the sending mailbox and the From address may send (*scopes*: see ``allows``)."""
        if not self._configured(scopes):
            return False
        sender = self.sender_mailbox(from_email)
        return self.allows(sender, "send", scopes=scopes) and (
            sender == normalize_mailbox(from_email) or self.allows(from_email, "send", scopes=scopes)
        )
