from core.models import AuthoredModel, ProjectControlModel

from django.db import models


class GoogleGmailAccount(AuthoredModel, ProjectControlModel):

    # gmail address
    gmail_address = models.CharField(
        max_length=128,
        unique=True,
        help_text="Google Gmail Address",
    )

    # google app password xxxx xxxx xxxx xxxx
    password = models.TextField(
        help_text="Google Gmail Password",
    )

    def __str__(self):
        return self.gmail_address
