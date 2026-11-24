"""HTTP clients for Custom endpoint providers that refuse redirects.

``ensure_public_host`` checks only the configured host. The OpenAI SDK and LiteLLM's Anthropic handler both follow
redirects, so a public endpoint answering ``307 Location: http://10.0.0.5/`` would otherwise make the server call its
own network. A response hook raises on any 3xx before httpx follows it. ``NoRedirectLitellmModel`` builds a client
for every model request, inside the running loop (an async client is bound to its loop, and sync callers use a fresh
loop per call), and passes it to ``litellm.acompletion`` as ``client``. It cannot travel in ``ModelSettings.extra_args``:
the Agents SDK copies and JSON-serializes model settings on every run.
"""

import dataclasses
from functools import cache

from django.views.decorators.debug import sensitive_variables

from .presets import ANTHROPIC_FORMAT

REDIRECT_REFUSED = "The AI provider answered with a redirect; System Intelligence does not follow redirects."


class RedirectRefused(Exception):
    """A custom endpoint answered with a redirect."""


async def refuse_redirects(response) -> None:
    if 300 <= response.status_code < 400:
        raise RedirectRefused(REDIRECT_REFUSED)


@sensitive_variables()
def no_redirect_client(provider, *, api_key: str, base_url: str):
    """The ``client`` LiteLLM should use for *provider*: an ``AsyncHTTPHandler`` (Anthropic format) or an
    ``AsyncOpenAI`` (OpenAI format), both with the redirect-refusing hook."""
    timeout = provider.request_timeout_seconds
    hooks = {"response": [refuse_redirects]}
    if provider.effective_api_format == ANTHROPIC_FORMAT:
        from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

        return AsyncHTTPHandler(timeout=timeout, event_hooks=hooks)
    import httpx
    from openai import AsyncOpenAI

    http_client = httpx.AsyncClient(timeout=timeout, event_hooks=hooks, follow_redirects=False)
    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, http_client=http_client)


@dataclasses.dataclass(frozen=True)
class _ClientSpec:
    request_timeout_seconds: int
    effective_api_format: str


@cache
def _model_class():
    from agents.extensions.models.litellm_model import LitellmModel

    class NoRedirectLitellmModel(LitellmModel):
        def __init__(self, *, client_spec: _ClientSpec, **kwargs):
            super().__init__(**kwargs)
            self._client_spec = client_spec

        async def _fetch_response(self, system_instructions, input, model_settings, *args, **kwargs):
            client = no_redirect_client(self._client_spec, api_key=self.api_key, base_url=self.base_url)
            extra_args = {**(model_settings.extra_args or {}), "client": client}
            settings = dataclasses.replace(model_settings, extra_args=extra_args)
            return await super()._fetch_response(system_instructions, input, settings, *args, **kwargs)

    return NoRedirectLitellmModel


def no_redirect_model(provider, **model_kwargs):
    """A ``LitellmModel`` for a Custom endpoint *provider* whose every request uses a redirect-refusing client."""
    spec = _ClientSpec(provider.request_timeout_seconds, provider.effective_api_format)
    return _model_class()(client_spec=spec, **model_kwargs)
