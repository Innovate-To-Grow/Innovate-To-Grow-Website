"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

django_application = get_asgi_application()

from system_intelligence.admin.adk_web import (  # noqa: E402
    SystemIntelligenceADKRouter,
    get_protected_system_intelligence_adk_asgi_application,
)

application = SystemIntelligenceADKRouter(
    django_application,
    get_protected_system_intelligence_adk_asgi_application(),
)
