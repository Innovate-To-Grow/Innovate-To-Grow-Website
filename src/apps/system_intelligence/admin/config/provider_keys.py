"""Admin pages of one AI provider: install its API key, remove it, and test a call.

Unfold detail actions (``permissions=["change"]``), so only staff granted the System Intelligence app reach them.
Successful POSTs redirect to the change page; ``sensitive_post_parameters`` / ``sensitive_variables`` keep the key out
of error reports, and nothing submitted is stored in the session or cache.
"""

import logging
from copy import copy

from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from unfold.decorators import action

from apps.system_intelligence.services.agents.providers.keys import ProviderKeyError, install_api_key, remove_api_key
from apps.system_intelligence.services.agents.providers.presets import suggested_models

from .provider_forms import API_KEY_FIELD, InstallApiKeyForm, RemoveApiKeyForm, TestConnectionForm

logger = logging.getLogger(__name__)
TEMPLATE = "admin/system_intelligence/provider_page.html"
PROBE_PROMPT = "Reply with exactly: OK"


class ProviderKeyActionsMixin:
    actions_detail = ["install_key_action", "test_connection_action", "remove_key_action"]

    @action(description="Install API key", url_path="install-key", icon="key", permissions=["change"])
    @method_decorator(csrf_protect)
    @method_decorator(sensitive_post_parameters(API_KEY_FIELD))
    @sensitive_variables()
    def install_key_action(self, request, object_id):
        provider, posted = self._provider(request, object_id)
        form = InstallApiKeyForm(request.POST if posted else None)
        if posted and form.is_valid():
            try:
                install_api_key(provider, form.cleaned_data[API_KEY_FIELD])
            except ProviderKeyError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request, f"Installed an API key ending in …{provider.key_hint}. Test it, then enable the provider."
                )
                return self._back(provider)
        return self._page(request, provider, "Install API key", form, "Install key")

    @action(description="Remove API key", url_path="remove-key", icon="key_off", permissions=["change"])
    @method_decorator(csrf_protect)
    def remove_key_action(self, request, object_id):
        provider, posted = self._provider(request, object_id)
        form = RemoveApiKeyForm(request.POST if posted else None)
        if posted and form.is_valid():
            remove_api_key(provider)
            messages.success(request, "Removed the API key and disabled the provider.")
            return self._back(provider)
        return self._page(request, provider, "Remove API key", form, "Remove key")

    @action(description="Test connection", url_path="test-connection", icon="science", permissions=["change"])
    @method_decorator(csrf_protect)
    def test_connection_action(self, request, object_id):
        provider, posted = self._provider(request, object_id)
        suggestions = suggested_models(provider.preset)
        initial = {"model_id": suggestions[0]} if suggestions else None
        form = TestConnectionForm(request.POST if posted else None, initial=initial, suggestions=suggestions)
        if posted and form.is_valid():
            self._run_probe(request, provider, form.cleaned_data["model_id"].strip())
            return self._back(provider)
        return self._page(request, provider, "Test connection", form, "Send test request")

    def _run_probe(self, request, provider, model_id):
        from apps.system_intelligence.services.agents import run_tool_free_agent
        from apps.system_intelligence.services.agents.providers.error_messages import provider_error_message

        if not provider.key_configured:
            messages.error(request, "Install an API key first.")
            return
        probe = copy(provider)
        probe.is_enabled = True  # a test may run before the provider is enabled
        try:
            result = run_tool_free_agent(
                system_text="You are a connectivity check.",
                input_data=PROBE_PROMPT,
                aws_config=None,
                model_id=model_id,
                max_tokens=16,
                temperature=None,
                include_temperature=False,
                agent_name="system_intelligence_provider_test",
                provider=probe,
            )
        except Exception as exc:  # noqa: BLE001 - every failure is reported as fixed text
            logger.warning("AI provider test failed for %s", provider.pk, exc_info=True)
            messages.error(request, f"Test failed: {provider_error_message(exc, f'The AI provider {provider.name!r}')}")
            return
        reply = (result.text or "").strip()[:80]
        if not reply:
            messages.warning(request, f"{model_id} answered with no text; check its output token limit.")
            return
        messages.success(
            request, f'Test passed. {model_id} replied: "{reply}" ({result.usage.get("totalTokens", 0)} tokens).'
        )

    def _provider(self, request, object_id):
        if request.method not in {"GET", "POST"}:
            raise Http404("Unsupported method.")
        provider = self.get_object(request, unquote(str(object_id)))
        if provider is None:
            raise Http404("AI provider not found.")
        return provider, request.method == "POST"

    def _back(self, provider):
        return HttpResponseRedirect(reverse("admin:system_intelligence_llmproviderconfig_change", args=[provider.pk]))

    def _page(self, request, provider, title, form, submit_label):
        context = {
            **self.admin_site.each_context(request),
            "title": f"{title}: {provider.name}",
            "provider": provider,
            "form": form,
            "submit_label": submit_label,
            "change_url": reverse("admin:system_intelligence_llmproviderconfig_change", args=[provider.pk]),
        }
        return TemplateResponse(request, TEMPLATE, context)
