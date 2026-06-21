def estimate_context_window(model_id: str | None) -> int:
    """Return a conservative context-window estimate for the active Bedrock model."""
    normalized = (model_id or "").lower()
    if "opus" in normalized:
        return 200_000
    if "sonnet" in normalized:
        return 200_000
    return 64_000
