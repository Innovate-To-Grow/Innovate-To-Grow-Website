"""Validation tests for the `frozen_page` block type."""

import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import FrozenPage, validate_block_data


class FrozenPageBlockValidationTests(TestCase):
    def setUp(self):
        self.published = FrozenPage.objects.create(
            source_url="https://example.com/",
            slug="published-page",
            status="published",
            frozen_html="<!DOCTYPE html><html></html>",
        )
        self.draft = FrozenPage.objects.create(
            source_url="https://example.com/draft",
            slug="draft-page",
            status="draft",
            frozen_html="<!DOCTYPE html><html></html>",
        )

    def test_requires_frozen_page_id(self):
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {})

    def test_rejects_invalid_uuid(self):
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {"frozen_page_id": "not-a-uuid"})

    def test_rejects_unknown_id(self):
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {"frozen_page_id": str(uuid.uuid4())})

    def test_rejects_unpublished_page(self):
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {"frozen_page_id": str(self.draft.pk)})

    def test_rejects_published_but_not_captured(self):
        empty = FrozenPage.objects.create(
            source_url="https://example.com/empty", slug="empty", status="published", frozen_html=""
        )
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {"frozen_page_id": str(empty.pk)})

    def test_accepts_published_page(self):
        validate_block_data("frozen_page", {"frozen_page_id": str(self.published.pk)})

    def test_rejects_out_of_range_height(self):
        with self.assertRaises(ValidationError):
            validate_block_data("frozen_page", {"frozen_page_id": str(self.published.pk), "height": "99999"})

    def test_accepts_valid_height(self):
        validate_block_data("frozen_page", {"frozen_page_id": str(self.published.pk), "height": "800"})
