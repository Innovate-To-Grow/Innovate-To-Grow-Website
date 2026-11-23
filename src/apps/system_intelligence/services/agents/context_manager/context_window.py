def estimate_context_window(model_id: str | None, provider=None) -> int:
    """Return a conservative context-window estimate for the configured model.

    An API-key *provider* uses its configured window or LiteLLM's model list; Bedrock keeps the name heuristic."""
    if provider is not None:
        from ..providers.capabilities import provider_context_window

        return provider_context_window(model_id or "", provider)
    normalized = (model_id or "").lower()
    if "opus" in normalized:
        return 200_000
    if "sonnet" in normalized:
        return 200_000
    return 64_000
