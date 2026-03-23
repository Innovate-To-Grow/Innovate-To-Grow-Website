from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class HomepagePageMigrationTests(TransactionTestCase):
    reset_sequences = True

    migrate_from = ("pages", "0015_ensure_cms_tables")
    migrate_to = ("pages", "0016_sitesettings_homepage_page")

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps

        CMSPage = old_apps.get_model("pages", "CMSPage")
        SiteSettings = old_apps.get_model("pages", "SiteSettings")

        self.homepage = CMSPage.objects.create(
            slug="migration-home",
            route="/home-during-event",
            title="Migration Home",
            status="published",
        )
        SiteSettings.objects.create(
            pk=1,
            homepage_mode="post-event",
            homepage_route="/home-during-event",
        )

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def test_backfills_homepage_page_from_existing_route(self):
        SiteSettings = self.apps.get_model("pages", "SiteSettings")

        settings = SiteSettings.objects.get(pk=1)
        self.assertEqual(str(settings.homepage_page_id), str(self.homepage.pk))
