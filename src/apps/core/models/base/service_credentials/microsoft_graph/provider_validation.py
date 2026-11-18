"""Validating a Graph configuration: its deny mailbox, sending limits, and changes that email sending forbids."""

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from .access_check import takeover_problem
from .certificate import MicrosoftGraphCertificate
from .mailboxes import is_deny_mailbox, normalize_mailbox

TAKEOVER_REFUSED = (
    "Mail → Notification Delivery sends email through Microsoft Graph, so this configuration can become the active "
    "one only when email could switch to it: {problem}"
)
# The Graph application permission Message Trace needs: tenant-wide, beyond the InfoSec approval for mail access.
MESSAGE_TRACE_ROLE = "ExchangeMessageTrace.Read.All"
MESSAGE_TRACE_NEEDS_REVIEW = (
    f"Message Trace needs the tenant-wide {MESSAGE_TRACE_ROLE} permission, which is beyond the InfoSec approval: "
    "record the InfoSec exception reference first."
)
SENDING_APP_CHANGE = (
    "Mail → Notification Delivery sends email through Microsoft Graph with this configuration, so its Entra "
    "application cannot change. Switch Notification Delivery to another provider first; switching back to Microsoft "
    "Graph then runs the go-live checks for the new application."
)


def _email_sends_through_graph() -> bool:
    from ..email import EmailServiceConfig  # email imports this package

    return EmailServiceConfig.objects.filter(is_active=True, provider=EmailServiceConfig.Provider.GRAPH).exists()


class GraphProviderValidationMixin:
    """``clean`` and its checks for ``MicrosoftGraphProviderConfig``."""

    def clean(self):
        super().clean()
        errors = {}
        if self.tenant_id and not is_entra_tenant(self.tenant_id):
            errors["tenant_id"] = "Use the tenant GUID or a verified domain such as contoso.onmicrosoft.com."
        if self.client_id and not is_guid(self.client_id):
            errors["client_id"] = "The application (client) ID must be a GUID."
        if self.mailbox and not is_exchange_mailbox(self.mailbox):
            errors["mailbox"] = "Enter the mailbox email address / user principal name, or its object ID (GUID)."
        self.access_check_deny_mailbox = normalize_mailbox(self.access_check_deny_mailbox)
        self.permission_exception_reference = str(self.permission_exception_reference or "").strip()
        if self.access_check_deny_mailbox and not is_deny_mailbox(self.access_check_deny_mailbox):
            errors["access_check_deny_mailbox"] = "Enter the plain email address of the designated test mailbox."
        elif self.access_check_deny_mailbox and self.access_check_deny_mailbox == normalize_mailbox(self.mailbox):
            errors["access_check_deny_mailbox"] = "The deny mailbox must not be the sender mailbox."
        changed = self._application_field_changed_under_a_certificate()
        if changed:
            errors.setdefault(
                changed,
                "Remove the installed certificates before changing the Entra application, then install the "
                "certificate registered for the new application.",
            )
        for field, message in self._sending_change_errors().items():
            errors.setdefault(field, message)
        for field, message in self._sending_limit_errors().items():
            errors.setdefault(field, message)
        if self._message_trace_needs_review():
            errors.setdefault("message_trace_enabled", MESSAGE_TRACE_NEEDS_REVIEW)
        if errors:
            raise ValidationError(errors)

    def _message_trace_needs_review(self) -> bool:
        """Where go-live evidence is required, Message Trace stays off until InfoSec approved its permission."""
        if not self.message_trace_enabled or not settings.GRAPH_REQUIRE_ACCESS_EVIDENCE:
            return False
        approved = MESSAGE_TRACE_ROLE in settings.GRAPH_APPROVED_APPLICATION_ROLES
        return not (approved or self.permission_exception_reference)

    def _sending_limit_errors(self) -> dict:
        """The limits must fit together: no message, and no hour, may hold more recipients than the day allows."""
        day = self.recipients_per_day_limit
        if not isinstance(day, int) or isinstance(day, bool):
            return {}  # the field's own validation reports it
        checks = (
            ("max_recipients_per_message", "One message cannot have more recipients than the day's limit allows."),
            ("external_recipients_per_hour_limit", "An hourly limit cannot be above the recipients per day limit."),
            ("internal_recipients_per_hour_limit", "An hourly limit cannot be above the recipients per day limit."),
        )
        return {
            field: message
            for field, message in checks
            if isinstance(getattr(self, field), int) and getattr(self, field) > day
        }

    def _application_field_changed_under_a_certificate(self) -> str:
        """A certificate is tested for one tenant and app, so it never silently follows a change of either.

        Returns the name of the changed field while a current or previous certificate is installed, else "".
        """
        if self._state.adding:
            return ""
        stored = type(self).objects.filter(pk=self.pk).values_list("tenant_id", "client_id").first()
        if stored is None or stored == (self.tenant_id, self.client_id):
            return ""
        if not self.certificates.filter(state__in=MicrosoftGraphCertificate.LIVE_STATES).exists():
            return ""
        return "tenant_id" if stored[0] != self.tenant_id else "client_id"

    def _sending_change_errors(self) -> dict:
        """While email is sent through Microsoft Graph, moving it to another Entra app or certificate is a go-live.

        Activating another config, or giving the active one another tenant or app, would send email with an app and
        certificate the go-live checks have not seen, so it needs what switching email to Graph needs
        (``takeover_problem``). Rotating the certificate of the active config is not covered: that check needs the
        new certificate installed first.
        """
        if not self.is_active or not _email_sends_through_graph():
            return {}
        stored = None
        if not self._state.adding:
            stored = type(self).objects.filter(pk=self.pk).values_list("is_active", "tenant_id", "client_id").first()
        if stored is not None and stored[0]:
            if stored[1:] == (self.tenant_id, self.client_id):
                return {}
            return {"tenant_id" if stored[1] != self.tenant_id else "client_id": SENDING_APP_CHANGE}
        problem = takeover_problem(self)
        return {"is_active": TAKEOVER_REFUSED.format(problem=problem)} if problem else {}
