import logging

from django.core.cache import cache

from ..clients._aws import get_management_client
from .discovery import fetch_foundation_models, fetch_inference_profiles, resolve_profile_model

logger = logging.getLogger(__name__)

MODEL_CACHE_KEY = "bedrock_available_models_v2"
MODEL_CACHE_TTL = 600


def get_available_models(force_refresh=False):
    """Return available Bedrock models grouped by provider."""
    if not force_refresh:
        cached = cache.get(MODEL_CACHE_KEY)
        if cached is not None:
            return cached
    try:
        result = fetch_models_from_aws()
        cache.set(MODEL_CACHE_KEY, result, MODEL_CACHE_TTL)
        return result
    except Exception:
        logger.exception("Failed to fetch Bedrock models from AWS")
        return []


def fetch_models_from_aws():
    mgmt = get_management_client()
    foundation_models = fetch_foundation_models(mgmt)
    model_metadata = foundation_models.copy()
    profile_base_ids = set()
    grouped = {}
    for profile in fetch_inference_profiles(mgmt):
        model_id, details = resolve_profile_model(mgmt, profile, model_metadata)
        modalities = details.get("outputModalities")
        if modalities and "TEXT" not in modalities:
            continue
        profile_base_ids.add(model_id)
        profile_id = profile["inferenceProfileId"]
        provider = details.get("providerName") or "Other"
        grouped.setdefault(provider, []).append((profile_id, profile.get("inferenceProfileName") or profile_id))
    for model_id, details in foundation_models.items():
        if model_id not in profile_base_ids:
            provider = details.get("providerName") or "Other"
            grouped.setdefault(provider, []).append((model_id, details.get("modelName") or model_id))
    return [(provider, sorted(models, key=lambda model: model[1])) for provider, models in sorted(grouped.items())]


def normalize_bedrock_model_id(model_id: str) -> str:
    model_id = (model_id or "").strip()
    if model_id.startswith("bedrock/"):
        return model_id.removeprefix("bedrock/")
    return model_id


def get_available_model_ids(force_refresh=False) -> set[str]:
    model_ids = set()
    for _group, models in get_available_models(force_refresh=force_refresh):
        model_ids.update(normalize_bedrock_model_id(model_id) for model_id, _name in models)
    return model_ids


def is_available_bedrock_model_id(model_id: str) -> bool:
    normalized_model_id = normalize_bedrock_model_id(model_id)
    if not normalized_model_id:
        return False
    if normalized_model_id in get_available_model_ids():
        return True
    return normalized_model_id in get_available_model_ids(force_refresh=True)
