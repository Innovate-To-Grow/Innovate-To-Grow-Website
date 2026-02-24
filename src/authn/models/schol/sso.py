from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


class SSOProfile(ProjectControlModel):
    # foreign key to User
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # school profile
    pass
