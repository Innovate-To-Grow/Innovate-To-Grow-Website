from django.db import models
import uuid

from core.models.base import TimeStampedModel

class Version(TimeStampedModel):

    pass

    # this feature can package all website data in to static files and no need for backend boot up to load the web.