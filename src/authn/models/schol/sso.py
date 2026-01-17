from django.contrib.auth.models import User
from django.db import models

from core.models import ProjectControlModel


class SSOProfile(ProjectControlModel):
    # foreign key to User
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # school profile
    pass
    # add with sso profile
