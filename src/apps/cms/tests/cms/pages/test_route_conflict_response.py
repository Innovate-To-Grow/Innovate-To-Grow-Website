import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.cms.admin.cms.page_admin.editor.responses import route_conflict_response
from apps.cms.models import CMSPage


class RouteConflictResponseTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_invalid_route_returns_validation_message(self):
        # An empty/invalid route fails validate_cms_route and reports is_valid False.
        with patch(
            "apps.cms.admin.cms.page_admin.editor.responses.validate_cms_route",
            side_effect=__import__("django.core.exceptions", fromlist=["ValidationError"]).ValidationError(
                ["Route cannot be blank."]
            ),
        ):
            response = route_conflict_response(self.factory.get("/route-conflict/", {"route": "bad"}))
        body = json.loads(response.content)
        self.assertFalse(body["is_valid"])
        self.assertEqual(body["message"], "Route cannot be blank.")
        self.assertFalse(body["has_conflict"])

    def test_excludes_current_page_from_conflict_check(self):
        page = CMSPage.objects.create(slug="self", route="/self-route", title="Self", status="published")
        response = route_conflict_response(
            self.factory.get("/route-conflict/", {"route": "/self-route", "page_id": str(page.pk)})
        )
        body = json.loads(response.content)
        # The page is excluded from the conflict query, so no conflict reported.
        self.assertTrue(body["is_valid"])
        self.assertFalse(body["has_conflict"])
