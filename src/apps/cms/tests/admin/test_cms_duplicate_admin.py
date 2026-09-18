from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.authn.models import Member
from apps.cms.models import CMSBlock, CMSPage

CHANGELIST_URL = "/admin/cms/cmspage/"


class CMSPageDuplicateActionTests(TestCase):
    """Tests for the changelist bulk action (select pages -> "Duplicate selected pages as drafts")."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_superuser(
            password="testpass123",
            first_name="Duplicate",
            last_name="Admin",
        )
        self.client = APIClient()
        self.client.force_login(self.staff)
        self.page = CMSPage.objects.create(
            slug="fall-event",
            route="/fall-event",
            title="Fall Event",
            status="published",
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            admin_label="Intro",
            data={"body_html": "<p>Intro</p>"},
        )

    def _run_action(self, *pages):
        return self.client.post(
            CHANGELIST_URL,
            {"action": "duplicate_pages", "_selected_action": [str(page.pk) for page in pages]},
        )

    def _message_texts(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_action_is_listed_in_the_changelist_dropdown(self):
        response = self.client.get(CHANGELIST_URL)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="duplicate_pages"')
        self.assertContains(response, "Duplicate selected pages as drafts")

    def test_single_selection_creates_draft_copy_and_opens_it(self):
        response = self._run_action(self.page)

        copy = CMSPage.objects.get(slug="fall-event-copy")
        self.assertRedirects(
            response,
            reverse("admin:cms_cmspage_change", args=[copy.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(copy.status, "draft")
        self.assertEqual(copy.route, "/fall-event-copy")
        self.assertEqual(copy.title, "Fall Event (Copy)")
        self.assertEqual(list(copy.blocks.values_list("admin_label", flat=True)), ["Intro"])
        self.assertEqual(self.page.blocks.count(), 1)

        texts = self._message_texts(response)
        self.assertEqual(len(texts), 1)
        self.assertIn("Created draft copy", texts[0])
        self.assertIn(reverse("admin:cms_cmspage_change", args=[copy.pk]), texts[0])

    def test_multiple_selection_stays_on_changelist_and_links_every_copy(self):
        other = CMSPage.objects.create(slug="spring-event", route="/spring-event", title="Spring Event", status="draft")

        response = self._run_action(self.page, other)

        self.assertRedirects(response, CHANGELIST_URL, fetch_redirect_response=False)
        first = CMSPage.objects.get(slug="fall-event-copy")
        second = CMSPage.objects.get(slug="spring-event-copy")
        texts = self._message_texts(response)
        self.assertEqual(len(texts), 1)
        self.assertIn("Created 2 draft copies", texts[0])
        self.assertIn(reverse("admin:cms_cmspage_change", args=[first.pk]), texts[0])
        self.assertIn(reverse("admin:cms_cmspage_change", args=[second.pk]), texts[0])

    def test_failed_page_is_reported_without_blocking_the_others(self):
        # A reserved-prefix route can never receive a valid "-copy" route.
        broken = CMSPage.objects.create(slug="legacy", route="/admin/legacy", title="Legacy", status="draft")

        response = self._run_action(self.page, broken)

        self.assertRedirects(response, CHANGELIST_URL, fetch_redirect_response=False)
        self.assertTrue(CMSPage.objects.filter(slug="fall-event-copy").exists())
        self.assertFalse(CMSPage.objects.filter(slug="legacy-copy").exists())
        texts = self._message_texts(response)
        self.assertTrue(any('Could not duplicate "Legacy"' in text for text in texts), texts)
        self.assertTrue(any("Created 1 draft copy:" in text for text in texts), texts)

    def test_action_requires_cms_app_access(self):
        outsider = Member.objects.create_user(
            password="testpass123",
            first_name="No",
            last_name="Access",
            is_active=True,
            is_staff=True,
        )
        self.client.force_login(outsider)

        response = self._run_action(self.page)

        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(CMSPage.objects.filter(slug="fall-event-copy").exists())
