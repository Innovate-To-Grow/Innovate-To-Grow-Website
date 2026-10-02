"""A stale stored session must not break the public CMS endpoints.

The SPA sends whatever access token local storage holds with every request; DRF authenticates before it checks
permissions, so a strict ``JWTAuthentication`` would 401 these ``AllowAny`` reads. Endpoints that never look at
the caller run no authentication; the ones that do (draft preview, page-view attribution) still honour a valid
token and treat a bad one as anonymous.
"""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import Member
from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage, NewsArticle


class PublicCMSEndpointsStaleBearerTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.home = CMSPage.objects.create(slug="home", route="/", title="Home", status="published")
        self.about = CMSPage.objects.create(slug="about", route="/about", title="About", status="published")
        CMSBlock.objects.create(
            page=self.about, block_type="rich_text", sort_order=0, data={"body_html": "<p>About us</p>"}
        )
        CMSEmbedWidget.objects.create(page=self.about, slug="about-widget", admin_label="About", block_sort_orders=[0])
        self.article = NewsArticle.objects.create(
            source_guid="guid-1",
            title="Headline",
            source_url="https://example.com/headline",
            summary="Summary.",
            published_at=timezone.now(),
        )
        cache.set("cms:preview:token-1", {"slug": "preview", "title": "Preview", "blocks": []}, timeout=600)

    def assert_reads_as_anonymous(self, url, **kwargs):
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(url, **kwargs, **extra))

    def test_layout(self):
        self.assert_reads_as_anonymous("/layout/")

    def test_embed_hosts(self):
        self.assert_reads_as_anonymous("/cms/embed-hosts/")

    def test_homepage(self):
        self.assert_reads_as_anonymous("/cms/homepage/")

    def test_page(self):
        self.assert_reads_as_anonymous("/cms/pages/about/")

    def test_unknown_page(self):
        self.assert_reads_as_anonymous("/cms/pages/missing/")

    def test_embed_widget(self):
        self.assert_reads_as_anonymous("/cms/embed/about-widget/")

    def test_preview_token(self):
        self.assert_reads_as_anonymous("/cms/preview/token-1/")

    def test_expired_preview_token(self):
        self.assert_reads_as_anonymous("/cms/preview/no-such-token/")

    def test_news_list(self):
        self.assert_reads_as_anonymous("/news/")

    def test_news_detail(self):
        self.assert_reads_as_anonymous(f"/news/{self.article.pk}/")

    def test_missing_news_detail(self):
        self.assert_reads_as_anonymous(f"/news/{uuid.uuid4()}/")


class CMSDraftPreviewIdentityTests(TestCase):
    """``?preview=true`` shows a draft to a member with cms access; a stale token is just anonymous."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")
        self.editor = Member.objects.create_user(password="testpass123", is_staff=True, admin_apps=["cms"])
        self.outsider = Member.objects.create_user(password="testpass123", is_staff=True, admin_apps=["event"])

    def get_draft(self, **extra):
        return self.client.get("/cms/pages/draft/", {"preview": "true"}, **extra)

    def test_valid_bearer_with_cms_access_sees_the_draft(self):
        response = self.get_draft(HTTP_AUTHORIZATION=valid_bearer_header(self.editor))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Draft")

    def test_valid_bearer_without_cms_access_does_not(self):
        response = self.get_draft(HTTP_AUTHORIZATION=valid_bearer_header(self.outsider))

        self.assertEqual(response.status_code, 404)

    def test_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(self, self.get_draft)

    def test_stale_bearer_never_sees_the_draft(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                self.assertEqual(self.get_draft(HTTP_AUTHORIZATION=header).status_code, 404)


class PageViewAttributionTests(TestCase):
    """A valid token attributes the page view to its member; a stale one is recorded as anonymous."""

    URL = "/analytics/pageview/"

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(password="testpass123", is_active=True)
        patcher = patch("apps.cms.views.analytics.enqueue")
        self.enqueue = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, **extra):
        return self.client.post(self.URL, {"path": "/about"}, format="json", **extra)

    def test_valid_bearer_attributes_the_view_to_the_member(self):
        response = self.post(HTTP_AUTHORIZATION=valid_bearer_header(self.member))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.enqueue.call_args.args[0]["member"], self.member)

    def test_no_bearer_records_no_member(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(self.enqueue.call_args.args[0]["member"])

    def test_stale_bearer_records_the_view_without_a_member(self):
        assert_stale_bearer_reads_as_anonymous(self, self.post)
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                self.enqueue.reset_mock()
                self.assertEqual(self.post(HTTP_AUTHORIZATION=header).status_code, 201)
                self.assertIsNone(self.enqueue.call_args.args[0]["member"])
