"""Whether email may switch to a provider: the Microsoft Graph and Gmail API go-live checks."""

from django.core.exceptions import ValidationError

from ..gmail_api import GmailApiProviderConfig, normalize_subject
from ..microsoft_graph import MicrosoftGraphProviderConfig
from ..microsoft_graph.access_check import takeover_problem
from .smtp import SMTPProviderConfig

GMAIL_ACTIVATION_REQUIRED = (
    "An active Gmail API configuration whose subject allow-list includes the From address, with a passed access "
    "check for the installed key, is required before activation."
)
GMAIL_NOT_READY = (
    "An active Gmail API configuration with an installed key and the From address on its subject allow-list is "
    "required."
)


class EmailActivationMixin:
    """``validate_activation`` and its provider checks for ``EmailServiceConfig``."""

    def validate_activation(self):
        if not self.is_active:
            return
        if self.provider == self.Provider.SES:
            from apps.core.models import AWSCredentialConfig

            if not AWSCredentialConfig.load().ses_configured:
                raise ValidationError({"provider": "Active AWS SES credentials are required before activation."})
        elif self.provider == self.Provider.SMTP and not SMTPProviderConfig.load().is_configured:
            raise ValidationError({"provider": "An active SMTP configuration is required before activation."})
        elif self.provider == self.Provider.GRAPH:
            self._validate_graph_activation()
        elif self.provider == self.Provider.GMAIL:
            self._validate_gmail_activation()

    def _validate_graph_activation(self):
        graph = MicrosoftGraphProviderConfig.load()
        if not graph.sending_ready(self.from_email):
            raise ValidationError(
                {
                    "provider": "An active Microsoft Graph configuration whose mailbox scope lets the sender "
                    "mailbox and the From address send is required before activation."
                }
            )
        if self._already_sending_through_graph():
            return
        problem = takeover_problem(graph)
        if problem:
            raise ValidationError({"provider": f"Email cannot switch to Microsoft Graph yet: {problem}"})

    def _already_sending_through_graph(self) -> bool:
        """The go-live checks guard the switch to Graph; editing a config that already sends through it is not one.

        Moving email that is already on Graph to another Graph config or Entra app is checked on that config instead
        (``MicrosoftGraphProviderConfig.clean``).
        """
        if not self.pk:
            return False
        stored = type(self).objects.filter(pk=self.pk).values_list("is_active", "provider").first()
        return stored == (True, self.Provider.GRAPH)

    def _validate_gmail_activation(self):
        """Switching email to the Gmail API, or changing its From address there, needs a passed access check that
        verified the From address with the installed key. Other saves while email already sends through it as this
        From address only need it to be able to send, so rotating the key never blocks unrelated edits."""
        gmail = GmailApiProviderConfig.load()
        if self._already_sending_through_gmail_as(self.from_email):
            if not gmail.sending_ready(self.from_email):
                raise ValidationError({"provider": GMAIL_NOT_READY})
            return
        if gmail.activation_problem(self.from_email):
            raise ValidationError({"provider": GMAIL_ACTIVATION_REQUIRED})

    def _already_sending_through_gmail_as(self, from_email: str) -> bool:
        if not self.pk:
            return False
        stored = type(self).objects.filter(pk=self.pk).values_list("is_active", "provider", "from_email").first()
        return bool(
            stored
            and stored[:2] == (True, self.Provider.GMAIL)
            and normalize_subject(stored[2]) == normalize_subject(from_email)
        )
