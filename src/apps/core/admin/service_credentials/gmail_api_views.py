"""Admin pages that install and remove the Gmail API service-account key and run its access check.

Each is its own URL (``get_urls``) wrapped by ``admin_site.admin_view``, which only checks ``is_staff``: the views
re-check that the user is a superuser themselves. Successful POSTs redirect to the change page (POST-redirect-GET),
nothing submitted goes to the session or cache, and ``sensitive_post_parameters`` / ``sensitive_variables`` keep the
key out of error reports.
"""

from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from apps.core.models import EmailServiceConfig
from apps.core.services.email.gmail.access_check import precondition_problem, run_access_check
from apps.core.services.email.gmail.key import install, removal
from apps.core.services.email.gmail.key.install import KeyChangeError

from .gmail_api_forms import KEY_FIELD, AccessCheckForm, InstallKeyForm, RemoveKeyForm
from .gmail_api_panel import ACCESS_CHECK_URL_NAME, INSTALL_URL_NAME, REMOVE_URL_NAME, URL_NAME_PREFIX, key_panel

TEMPLATE_DIR = "admin/core/gmailapiproviderconfig"
SUPERUSER_ONLY = "Only a superuser can manage the Gmail API key or run its access check."
EMAIL_STOPPED = (
    "Email is still set to the Gmail API and will fail until a key is installed. Switch Mail → Notification "
    "Delivery to another provider if this was not intended."
)


class GmailApiKeyViewsMixin:
    """Key and access-check pages for ``GmailApiProviderConfigAdmin``."""

    def get_key_urls(self):
        views = (
            ("key/install", INSTALL_URL_NAME, self.install_key_view),
            ("key/remove", REMOVE_URL_NAME, self.remove_key_view),
            ("access-check", ACCESS_CHECK_URL_NAME, self.run_access_check_view),
        )
        return [
            path(f"<path:object_id>/{route}/", self.admin_site.admin_view(view), name=name)
            for route, name, view in views
        ]

    @method_decorator(sensitive_post_parameters(KEY_FIELD))
    @sensitive_variables()
    def install_key_view(self, request, object_id):
        config = self._key_config(request, object_id)
        posted = request.method == "POST"
        form = InstallKeyForm(request.POST, request.FILES) if posted else InstallKeyForm()
        if posted and form.is_valid():
            try:
                test = install.install_key(config, form.parsed, actor=request.user)
            except KeyChangeError as exc:
                form.add_error(None, exc.message)
            else:
                messages.success(request, f"Installed key {config.key_id} for {config.service_account_email}.")
                level = messages.SUCCESS if test.outcome == install.ISSUED else messages.WARNING
                messages.add_message(request, level, f"{test.describe()} Run the access check before go-live.")
                return self._redirect_to_change(config)
        context = self._page_context(request, config, "Install the Gmail API key", form=form)
        return TemplateResponse(request, f"{TEMPLATE_DIR}/install_key.html", context)

    def remove_key_view(self, request, object_id):
        config = self._key_config(request, object_id)
        posted = request.method == "POST"
        form = RemoveKeyForm(request.POST) if posted else RemoveKeyForm()
        if posted and form.is_valid():
            try:
                result = removal.remove_key(
                    config,
                    reason=form.cleaned_data["reason"],
                    actor=request.user,
                    switch_to_ses=form.cleaned_data["switch_to_ses"],
                )
            except KeyChangeError as exc:
                form.add_error(None, exc.message)
            else:
                messages.success(request, f"Removed the Gmail API key {result.key_id}; this config is inactive now.")
                self._report_email(request, result.provider_switched)
                return self._redirect_to_change(config)
        context = self._page_context(request, config, "Remove the Gmail API key", form=form)
        return TemplateResponse(request, f"{TEMPLATE_DIR}/remove_key.html", context)

    def run_access_check_view(self, request, object_id):
        config = self._key_config(request, object_id)
        problem = precondition_problem(config)
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = AccessCheckForm(request.POST) if request.method == "POST" else AccessCheckForm()
        if request.method == "POST" and not problem and form.is_valid():
            report = run_access_check(config, send=form.cleaned_data["send"], breadth=form.cleaned_data["breadth"])
            level = messages.ERROR if report.failed else messages.SUCCESS if report.recorded else messages.WARNING
            messages.add_message(request, level, f"{report.summary()}. {report.conclusion()}")
            context = self._page_context(request, config, "Gmail API access check result", report=report)
            return TemplateResponse(request, f"{TEMPLATE_DIR}/access_check_result.html", context)
        context = self._page_context(request, config, "Run the Gmail API access check", form=form, problem=problem)
        return TemplateResponse(request, f"{TEMPLATE_DIR}/run_access_check.html", context)

    def _key_config(self, request, object_id):
        if not request.user.is_superuser:
            raise PermissionDenied(SUPERUSER_ONLY)
        config = self.get_object(request, unquote(object_id))
        if config is None:
            raise Http404("No Gmail API config matches this ID.")
        return config

    def _page_context(self, request, config, title, **extra):
        return {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.opts,
            "original": config,
            "gmail_key_panel": key_panel(request, config, actions=False),
            "from_email": EmailServiceConfig.load().from_email,
            "cancel_url": reverse(f"admin:{URL_NAME_PREFIX}_change", args=[config.pk]),
            **extra,
        }

    @staticmethod
    def _redirect_to_change(config):
        return HttpResponseRedirect(reverse(f"admin:{URL_NAME_PREFIX}_change", args=[config.pk]))

    @staticmethod
    def _report_email(request, switched: bool) -> None:
        if switched:
            messages.success(request, "Email delivery now uses AWS SES.")
            return
        email = EmailServiceConfig.load()
        if email.is_active and email.provider == EmailServiceConfig.Provider.GMAIL:
            messages.warning(request, EMAIL_STOPPED)
