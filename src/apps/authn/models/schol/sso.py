from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


class SSOProfile(ProjectControlModel):
    """
    Legacy placeholder kept importable for compatibility.

    This model has no backing migration in the current authn app, so it must
    remain abstract to avoid registering a reverse relation on Member that
    points at a non-existent table during test collection.
    """

    # foreign key to User
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # school profile and school sso field
    class Meta:
        abstract = True
