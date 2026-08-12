from django.core.management import get_commands
from django.test import SimpleTestCase


class CommandDiscoveryTests(SimpleTestCase):
    def test_authn_commands_are_discoverable(self):
        commands = get_commands()

        for name in ("createsuperuser", "ensure_default_admin", "migrate_locked", "sync_members_to_sheet"):
            self.assertEqual(commands[name], "apps.authn")
