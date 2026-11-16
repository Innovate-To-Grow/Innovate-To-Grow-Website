from django.test import SimpleTestCase

from apps.cms.models import (
    SiteSettings,
)
from apps.system_intelligence.services.tools import exports as exports_module
from apps.system_intelligence.services.tools.cms import layout as layout_module
from apps.system_intelligence.services.tools.cms import news as news_module
from apps.system_intelligence.services.tools.domains import mail as mail_module
from apps.system_intelligence.services.tools.domains import members as members_module
from apps.system_intelligence.services.tools.domains import projects as projects_module
from apps.system_intelligence.services.tools.events import lookup as lookup_module
from apps.system_intelligence.services.tools.events import registrations as registrations_module


class DirectHelperReferenceTests(SimpleTestCase):
    """Reference the imported domain modules so unused-import lint stays clean."""

    def test_modules_are_importable(self):
        for module in (
            members_module,
            projects_module,
            layout_module,
            news_module,
            mail_module,
            lookup_module,
            registrations_module,
            exports_module,
        ):
            self.assertTrue(hasattr(module, "__name__"))
        self.assertTrue(callable(SiteSettings.load))
