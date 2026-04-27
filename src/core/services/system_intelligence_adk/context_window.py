def estimate_context_window(model_id: str | None) -> int:
    """Return a conservative context-window estimate for the active Bedrock model."""
    normalized = (model_id or "").lower()
    if "anthropic" in normalized or "claude" in normalized:
        return 200_000
    if "llama" in normalized or "mistral" in normalized:
        return 128_000
    return 200_000
