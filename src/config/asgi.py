"""
ASGI config for the project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Deployment always sets DJANGO_SETTINGS_MODULE explicitly (ECS task definition /
# entrypoint). This default is only a fallback for a bare ``python`` invocation.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

django_application = get_asgi_application()

application = django_application
