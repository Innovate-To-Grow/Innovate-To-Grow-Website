"""The Microsoft Graph and Gmail API checks of ``verify_service_configs``: each provider is reported only while it is
selected or configured, and while it is active its mailbox scope or allow-list, its certificate or key, and its
access evidence are checked."""

from django.conf import settings

from apps.core.models import (
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
)
from apps.core.services.email.graph.credential import expiry
from apps.core.services.email.graph.credential.expiry import local_time_text


class ProviderChecksMixin:
    def _check_graph(self, email, failures: list[str], warnings: list[str]) -> bool:
        """Report Microsoft Graph only when it is selected or configured, so other setups stay quiet."""
        graph = MicrosoftGraphProviderConfig.load()
        graph_ok = bool(graph.pk) and graph.sending_ready(email.from_email)
        required = email.provider == "graph"
        if required or (graph.pk and graph.is_configured):
            self._report("MicrosoftGraphProviderConfig", graph, graph_ok, required=required)
        if graph.pk and graph.is_active:
            self._check_graph_scope_and_certificate(graph, email, required, failures, warnings)
        return graph_ok

    def _check_graph_scope_and_certificate(self, graph, email, required, failures, warnings) -> None:
        problems = failures if required else warnings
        if not graph.mailbox_scopes.exists():
            problems.append("MicrosoftGraphProviderConfig has no mailbox scope; Graph refuses every mailbox.")
        elif graph.is_configured and not graph.sending_ready(email.from_email):
            problems.append(
                "The Graph sending mailbox or the From address is not in the mailbox scope with send permission."
            )
        certificate = graph.current_certificate
        if certificate is None:
            problems.append("MicrosoftGraphProviderConfig has no installed certificate.")
            return
        self._check_graph_expiry(certificate, problems, warnings)

    @staticmethod
    def _check_graph_expiry(certificate, problems: list[str], warnings: list[str]) -> None:
        """Expired or not yet valid, and from ``GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`` before expiry, are problems
        (failures while Graph is selected); from ``GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`` before, a warning."""
        status = expiry.certificate_expiry(certificate)
        expires_at = local_time_text(certificate.not_after)
        if status.level == expiry.NOT_YET_VALID:
            valid_from = local_time_text(certificate.not_before)
            problems.append(f"The Microsoft Graph certificate is not valid until {valid_from}.")
        elif status.level == expiry.EXPIRED:
            problems.append(f"The Microsoft Graph certificate expired on {expires_at}.")
        elif status.level == expiry.CRITICAL:
            problems.append(
                f"The Microsoft Graph certificate expires on {expires_at} ({status.days_left} days, within "
                f"{settings.GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS}); install the renewed certificate now."
            )
        elif status.level == expiry.WARNING:
            warnings.append(
                f"The Microsoft Graph certificate expires on {expires_at} ({status.days_left} days); rotate it."
            )

    def _check_gmail(self, email, failures: list[str], warnings: list[str]) -> bool:
        """Report the Gmail API only when it is selected or configured. While it is selected, a key without a
        passed access check (after a rotation, say) is a failure: sends work, but the evidence is missing."""
        gmail = GmailApiProviderConfig.load()
        gmail_ok = gmail.sending_ready(email.from_email)
        required = email.provider == "gmail"
        if required or gmail.is_configured:
            self._report("GmailApiProviderConfig", gmail, gmail_ok, required=required)
        if not (gmail.pk and gmail.is_active):
            return gmail_ok
        problems = failures if required else warnings
        if not gmail.subjects.exists():
            problems.append("GmailApiProviderConfig has an empty allow-list; the Gmail API refuses every account.")
        elif not gmail.allows(email.from_email):
            problems.append("The From address is not on the Gmail API account allow-list.")
        if gmail.key_configured and gmail.activation_problem(email.from_email):
            problems.append(f"Gmail API: {gmail.activation_problem(email.from_email)}")
        return gmail_ok
