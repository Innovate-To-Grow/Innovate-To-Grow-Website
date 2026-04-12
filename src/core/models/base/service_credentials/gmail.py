from django.db import models


class GmailImportConfig(models.Model):
    """
    Gmail IMAP configuration for importing HTML templates from sent mail.

    Multiple configs can exist but only one may be active at a time.
    Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production Gmail Import').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )
    imap_host = models.CharField(
        max_length=254,
        blank=True,
        default="imap.gmail.com",
        verbose_name="IMAP Host",
    )
    gmail_username = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="Gmail Username",
        help_text="The Gmail account used to log in over IMAP and read sent messages.",
    )
    gmail_password = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Gmail Password",
        help_text="Gmail app password used for IMAP login.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gmail Import Config"
        verbose_name_plural = "Gmail Import Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        mailbox = self.gmail_username or "unconfigured"
        return f"{self.name}: {mailbox}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            GmailImportConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one."""
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return bool(self.imap_host and self.gmail_username and self.gmail_password)

    @property
    def mailbox(self):
        return self.gmail_username
