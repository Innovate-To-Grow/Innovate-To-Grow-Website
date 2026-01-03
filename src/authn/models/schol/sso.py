from django.contrib.auth.models import User
from django.db import models

from core.models.base import TimeStampedModel


class SSOProfile(TimeStampedModel):
    # foreign key to User
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # school profile
    pass
    # add with sso profile
