import logging

logger = logging.getLogger(__name__)


def fetch_foundation_models(mgmt):
    try:
        response = mgmt.list_foundation_models(byOutputModality="TEXT", byInferenceType="ON_DEMAND")
        return {model["modelId"]: model for model in response.get("modelSummaries", [])}
    except Exception:
        logger.warning("list_foundation_models failed")
        return {}


def fetch_inference_profiles(mgmt):
    try:
        for page in mgmt.get_paginator("list_inference_profiles").paginate(typeEquals="SYSTEM_DEFINED"):
            for profile in page.get("inferenceProfileSummaries", []):
                if profile.get("type") == "SYSTEM_DEFINED" and profile.get("status") == "ACTIVE":
                    yield profile
    except Exception:
        logger.warning("list_inference_profiles failed")


def resolve_profile_model(mgmt, profile, model_metadata):
    for model in profile.get("models", []):
        model_arn = model.get("modelArn", "")
        _, _, model_id = model_arn.partition(":foundation-model/")
        if model_id:
            if model_id not in model_metadata:
                model_metadata[model_id] = _fetch_foundation_model(mgmt, model_arn)
            return model_id, model_metadata[model_id]
    return "", {}


def _fetch_foundation_model(mgmt, model_arn):
    try:
        return mgmt.get_foundation_model(modelIdentifier=model_arn).get("modelDetails", {})
    except Exception:
        logger.warning("get_foundation_model failed for %s", model_arn)
        return {}
