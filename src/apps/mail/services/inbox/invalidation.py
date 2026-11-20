"""Drop the inbox's cached account and sender lists when a configuration they depend on is saved or deleted.

Connected from ``MailConfig.ready``. Each container drops only its own cache (production has no shared cache), so
the lists also expire on their own after a minute; and every read and send re-checks its configuration, so a stale
list never reaches a mailbox or sends as an address the configuration no longer allows. Saving a mailbox's
configuration also forgets whether it could connect (``health.reset``), so a fixed password shows the account again
at once instead of after the next poll.
"""

from django.db.models.signals import post_delete, post_save

DISPATCH_PREFIX = "mail_inbox_invalidate"


def register() -> None:
    from apps.core import models as core

    senders = (
        core.GmailAccessAccount,
        core.MicrosoftGraphProviderConfig,
        core.MicrosoftGraphMailboxScope,
        core.MicrosoftGraphCertificate,
        core.MicrosoftGraphAccessCheck,
        core.EmailServiceConfig,
        core.GmailApiProviderConfig,
        core.GmailApiSubject,
        core.AWSCredentialConfig,
        core.SMTPProviderConfig,
    )
    for model in senders:
        for signal in (post_save, post_delete):
            signal.connect(
                configuration_changed,
                sender=model,
                dispatch_uid=f"{DISPATCH_PREFIX}:{signal is post_save}:{model._meta.label}",
                weak=False,
            )


def configuration_changed(sender, instance=None, **kwargs) -> None:
    from apps.core import models as core

    from . import health
    from .accounts import GRAPH_ACCOUNT, IMAP_ACCOUNT, forget_accounts
    from .senders import forget_identities

    forget_accounts()
    forget_identities()
    if sender is core.GmailAccessAccount and instance is not None and instance.pk:
        health.reset([f"{IMAP_ACCOUNT}:{instance.pk}"])
    elif sender in (core.MicrosoftGraphProviderConfig, core.MicrosoftGraphMailboxScope, core.MicrosoftGraphCertificate):
        health.reset(prefix=f"{GRAPH_ACCOUNT}:")
