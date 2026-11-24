"""Admin-facing text for a failed call to an API-key provider, chosen by LiteLLM's exception type.

Provider error bodies can echo request details (a masked key, the base URL), so the text shown is always one of the
fixed templates below with only the provider's admin-given name filled in; the full exception goes to the logs.
"""

GENERIC = "{label} could not complete the request. See server logs for details."
_TEMPLATES = (
    (
        "ContextWindowExceededError",
        "The conversation is too long for this model's context window. Start a new chat or run /compact.",
    ),
    ("AuthenticationError", "{label} rejected the API key. Install a valid key on the AI provider page."),
    ("PermissionDeniedError", "{label} refused access to this model."),
    ("NotFoundError", "{label} does not serve this model. Check the model name."),
    ("RateLimitError", "{label} reported a rate limit or exhausted quota. Try again later."),
    ("Timeout", "{label} did not answer in time."),
    ("APIConnectionError", "Unable to reach {label}. Check network connectivity for the server and try again."),
    ("ServiceUnavailableError", "{label} is temporarily unavailable. Try again later."),
    ("InternalServerError", "{label} is temporarily unavailable. Try again later."),
    ("BadGatewayError", "{label} is temporarily unavailable. Try again later."),
    ("BadRequestError", "{label} rejected the request. Check the model name and settings."),
)


def _litellm_exception_types():
    try:
        from litellm import exceptions
    except Exception:  # noqa: BLE001
        return ()
    return tuple((getattr(exceptions, name, None), template) for name, template in _TEMPLATES)


def _chain(error: BaseException):
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def describe_provider_error(error: BaseException, label: str) -> str | None:
    """Fixed text for a LiteLLM error anywhere in *error*'s chain, or ``None`` when none is found."""
    from .http_clients import REDIRECT_REFUSED, RedirectRefused
    from .routing import ProviderConfigurationError

    types = [(cls, template) for cls, template in _litellm_exception_types() if isinstance(cls, type)]
    for current in _chain(error):
        if isinstance(current, ProviderConfigurationError):
            return str(current)
        if isinstance(current, RedirectRefused) or REDIRECT_REFUSED in str(current):
            return REDIRECT_REFUSED
        for cls, template in types:
            if isinstance(current, cls):
                return template.format(label=label)
    return None


def provider_error_message(error: BaseException | str, label: str) -> str:
    if isinstance(error, str):
        return error
    return describe_provider_error(error, label) or GENERIC.format(label=label)
