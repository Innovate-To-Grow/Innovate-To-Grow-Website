"""Tests for bedrock model catalog + helper functions (AWS mocked)."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.system_intelligence.services.bedrock.models.catalog import (
    MODEL_CACHE_KEY,
    fetch_models_from_aws,
    get_available_model_ids,
    get_available_models,
    is_available_bedrock_model_id,
    normalize_bedrock_model_id,
)
from apps.system_intelligence.services.bedrock.models.discovery import fetch_foundation_models


def inference_profile(profile_id, model_arn, **overrides):
    return {
        "type": "SYSTEM_DEFINED",
        "status": "ACTIVE",
        "inferenceProfileId": profile_id,
        "models": [{"modelArn": model_arn}],
        **overrides,
    }


class FetchFoundationModelsTest(SimpleTestCase):
    def test_indexes_on_demand_text_models_by_id(self):
        mgmt = MagicMock()
        model = {"modelId": "future.model", "providerName": "Future AI", "modelName": "Future Model"}
        mgmt.list_foundation_models.return_value = {"modelSummaries": [model]}
        self.assertEqual(fetch_foundation_models(mgmt), {"future.model": model})
        mgmt.list_foundation_models.assert_called_once_with(byOutputModality="TEXT", byInferenceType="ON_DEMAND")

    def test_swallows_aws_failure(self):
        mgmt = MagicMock()
        mgmt.list_foundation_models.side_effect = RuntimeError("boom")
        with patch("apps.system_intelligence.services.bedrock.models.discovery.logger.warning") as warn:
            result = fetch_foundation_models(mgmt)
        self.assertEqual(result, {})
        warn.assert_called_once_with("list_foundation_models failed")


class NormalizeModelIdTest(SimpleTestCase):
    def test_strips_bedrock_prefix(self):
        self.assertEqual(normalize_bedrock_model_id("bedrock/anthropic.claude"), "anthropic.claude")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_bedrock_model_id("  anthropic.claude  "), "anthropic.claude")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_bedrock_model_id(None), "")


class FetchModelsFromAwsTest(SimpleTestCase):
    def setUp(self):
        self.mgmt = MagicMock()
        self.mgmt.list_foundation_models.return_value = {"modelSummaries": []}
        self.paginate = self.mgmt.get_paginator.return_value.paginate
        self.paginate.return_value = []
        self.enterContext(
            patch(
                "apps.system_intelligence.services.bedrock.models.catalog.get_management_client", return_value=self.mgmt
            )
        )

    def test_empty_when_no_providers(self):
        self.assertEqual(fetch_models_from_aws(), [])

    def test_uses_aws_provider_for_global_profile_and_deduplicates_base_model(self):
        self.mgmt.list_foundation_models.return_value = {
            "modelSummaries": [
                {"modelId": "future.model", "providerName": "Future AI", "modelName": "Base Model"},
                {"modelId": "future.other", "providerName": "Future AI", "modelName": "Another Model"},
            ]
        }
        model_arn = "arn:aws:bedrock:us-west-2::foundation-model/future.model"
        self.paginate.return_value = [
            {"inferenceProfileSummaries": [inference_profile("application-profile", model_arn, type="APPLICATION")]},
            {
                "inferenceProfileSummaries": [
                    inference_profile("inactive-profile", model_arn, status="INACTIVE"),
                    inference_profile("global.future.model", model_arn, inferenceProfileName="Global Model"),
                ]
            },
        ]
        self.assertEqual(
            fetch_models_from_aws(),
            [("Future AI", [("future.other", "Another Model"), ("global.future.model", "Global Model")])],
        )
        self.paginate.assert_called_once_with(typeEquals="SYSTEM_DEFINED")
        self.mgmt.get_foundation_model.assert_not_called()

    def test_fetches_profile_only_model_details_once_across_pages(self):
        primary_arn = "arn:aws:bedrock:us-west-2::foundation-model/newvendor.model:0"
        secondary_arn = "arn:aws:bedrock:us-east-2::foundation-model/newvendor.model:0"
        self.paginate.return_value = [
            {
                "inferenceProfileSummaries": [
                    inference_profile("global.newvendor.model", primary_arn, inferenceProfileName="Global")
                ]
            },
            {
                "inferenceProfileSummaries": [
                    inference_profile("us.newvendor.model", secondary_arn, inferenceProfileName="US")
                ]
            },
        ]
        self.mgmt.get_foundation_model.return_value = {
            "modelDetails": {"providerName": "New Vendor", "outputModalities": ["TEXT"]}
        }
        self.assertEqual(
            fetch_models_from_aws(),
            [("New Vendor", [("global.newvendor.model", "Global"), ("us.newvendor.model", "US")])],
        )
        self.mgmt.get_foundation_model.assert_called_once_with(modelIdentifier=primary_arn)

    def test_excludes_known_non_text_profile(self):
        model_arn = "arn:aws:bedrock:us-west-2::foundation-model/future.image"
        self.paginate.return_value = [
            {"inferenceProfileSummaries": [inference_profile("global.future.image", model_arn)]}
        ]
        self.mgmt.get_foundation_model.return_value = {"modelDetails": {"outputModalities": ["IMAGE"]}}
        self.assertEqual(fetch_models_from_aws(), [])

    def test_falls_back_to_other_when_profile_details_unavailable(self):
        model_arn = "arn:aws:bedrock:us-west-2::foundation-model/future.model"
        self.paginate.return_value = [
            {"inferenceProfileSummaries": [inference_profile("global.future.model", model_arn)]}
        ]
        self.mgmt.get_foundation_model.side_effect = RuntimeError("no access")
        with self.assertLogs("apps.system_intelligence.services.bedrock.models.discovery", level="WARNING"):
            self.assertEqual(fetch_models_from_aws(), [("Other", [("global.future.model", "global.future.model")])])

    def test_keeps_foundation_models_when_profiles_unavailable(self):
        self.mgmt.list_foundation_models.return_value = {"modelSummaries": [{"modelId": "future.model"}]}
        self.paginate.side_effect = RuntimeError("no access")
        with self.assertLogs("apps.system_intelligence.services.bedrock.models.discovery", level="WARNING"):
            self.assertEqual(fetch_models_from_aws(), [("Other", [("future.model", "future.model")])])


class GetAvailableModelsCacheTest(SimpleTestCase):
    def setUp(self):
        cache.delete(MODEL_CACHE_KEY)

    def tearDown(self):
        cache.delete(MODEL_CACHE_KEY)

    def test_returns_cached_value_without_refetch(self):
        cached = [("Cached", [("c.model", "Cached Model")])]
        cache.set(MODEL_CACHE_KEY, cached)
        with patch("apps.system_intelligence.services.bedrock.models.catalog.fetch_models_from_aws") as fetch:
            result = get_available_models()
        self.assertEqual(result, cached)
        fetch.assert_not_called()

    def test_get_available_model_ids_normalizes(self):
        grouped = [("P", [("bedrock/anthropic.claude", "C"), ("amazon.titan", "T")])]
        with patch(
            "apps.system_intelligence.services.bedrock.models.catalog.get_available_models",
            return_value=grouped,
        ):
            ids = get_available_model_ids()
        self.assertEqual(ids, {"anthropic.claude", "amazon.titan"})

    def test_is_available_returns_false_for_empty_id(self):
        self.assertFalse(is_available_bedrock_model_id(""))

    def test_is_available_true_when_in_first_lookup(self):
        with patch(
            "apps.system_intelligence.services.bedrock.models.catalog.get_available_model_ids",
            return_value={"anthropic.claude"},
        ) as ids:
            self.assertTrue(is_available_bedrock_model_id("anthropic.claude"))
        ids.assert_called_once_with()  # no forced refresh needed
