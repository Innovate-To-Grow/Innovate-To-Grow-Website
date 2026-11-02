"""Admin pages that install, roll back and remove the Microsoft Graph certificate, and download it as a .cer file.

Each is its own URL (``get_urls``) wrapped by ``admin_site.admin_view``, which only checks ``is_staff``: the views
re-check access themselves. Installing a certificate requires permission to change the config; rollback and
removal remain superuser-only. Downloading the public certificate is open to whoever can view the config.
Successful POSTs redirect to the change page (POST-redirect-GET), and
nothing submitted goes to the session or cache. ``sensitive_post_parameters`` and ``sensitive_variables`` keep the
key and password out of error reports.
"""

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from apps.core.models import EmailServiceConfig
from apps.core.services.email.graph.credential import lifecycle, recovery
from apps.core.services.email.graph.credential.lifecycle import CertificateChangeError

from .microsoft_graph_certificate_forms import InstallCertificateForm, RemoveCertificatesForm
from .microsoft_graph_panel import (
    DOWNLOAD_URL_NAME,
    INSTALL_URL_NAME,
    REMOVE_URL_NAME,
    ROLLBACK_URL_NAME,
    URL_NAME_PREFIX,
    certificate_card,
)

TEMPLATE_DIR = "admin/core/microsoftgraphproviderconfig"
SUPERUSER_ONLY = "Only a superuser can roll back or remove Microsoft Graph certificates."
EMAIL_STOPPED = (
    "Email is still set to Microsoft Graph and will fail until a certificate is installed. Switch Mail → "
    "Notification Delivery to another provider if this was not intended."
)
SES_NOT_READY = "Email was not switched to AWS SES: SES is not ready. "
NOTHING_TO_REMOVE = "No certificate is installed, so there is nothing to remove."


class GraphCertificateViewsMixin:
    """Certificate pages for ``MicrosoftGraphProviderConfigAdmin``."""

    def get_certificate_urls(self):
        views = (
            ("install", INSTALL_URL_NAME, self.install_certificate_view),
            ("rollback", ROLLBACK_URL_NAME, self.rollback_certificate_view),
            ("remove", REMOVE_URL_NAME, self.remove_certificates_view),
            ("download", DOWNLOAD_URL_NAME, self.download_certificate_view),
        )
        return [
            path(f"<path:object_id>/certificate/{route}/", self.admin_site.admin_view(view), name=name)
            for route, name, view in views
        ]

    @method_decorator(sensitive_post_parameters())
    @sensitive_variables()
    def install_certificate_view(self, request, object_id):
        config = self._config(request, object_id)
        if not self.has_change_permission(request, config):
            raise PermissionDenied
        posted = request.method == "POST"
        form = InstallCertificateForm(request.POST, request.FILES) if posted else InstallCertificateForm()
        if posted and form.is_valid():
            try:
                certificate = lifecycle.install_certificate(config, form.parsed, actor=request.user)
            except CertificateChangeError as exc:
                form.add_error(form.field_for(exc.field), exc.message)
            else:
                check = f"Entra check: {certificate.get_entra_check_display()}."
                messages.success(request, f"Installed the certificate ({lifecycle.summary(certificate)}). {check}")
                return self._redirect_to_change(config)
        context = self._page_context(request, config, "Install Microsoft Graph certificate", form=form)
        return TemplateResponse(request, f"{TEMPLATE_DIR}/install_certificate.html", context)

    def rollback_certificate_view(self, request, object_id):
        config = self._certificate_config(request, object_id)
        if config.previous_certificate is None:
            messages.error(request, recovery.NO_PREVIOUS)
            return self._redirect_to_change(config)
        if request.method == "POST":
            try:
                restored = recovery.rollback_certificate(config, actor=request.user)
            except CertificateChangeError as exc:
                messages.error(request, exc.message)
            else:
                messages.success(request, f"Rolled back to the previous certificate ({lifecycle.summary(restored)}).")
            return self._redirect_to_change(config)
        context = self._page_context(request, config, "Roll back to the previous certificate")
        return TemplateResponse(request, f"{TEMPLATE_DIR}/rollback_certificate.html", context)

    def remove_certificates_view(self, request, object_id):
        config = self._certificate_config(request, object_id)
        if config.current_certificate is None and config.previous_certificate is None:
            messages.error(request, NOTHING_TO_REMOVE)
            return self._redirect_to_change(config)
        posted = request.method == "POST"
        form = RemoveCertificatesForm(request.POST) if posted else RemoveCertificatesForm()
        if posted and form.is_valid():
            try:
                result = recovery.remove_certificates(
                    config,
                    reason=form.cleaned_data["reason"],
                    actor=request.user,
                    switch_to_ses=form.cleaned_data["switch_to_ses"],
                )
            except CertificateChangeError as exc:
                form.add_error(exc.field if exc.field in form.fields else None, exc.message)
            else:
                self._report_removal(request, config, result, wanted_ses=form.cleaned_data["switch_to_ses"])
                return self._redirect_to_change(config)
        context = self._page_context(request, config, "Remove the Microsoft Graph certificates", form=form)
        return TemplateResponse(request, f"{TEMPLATE_DIR}/remove_certificates.html", context)

    def download_certificate_view(self, request, object_id):
        """The current certificate as DER (.cer): public data, what OIT registers on the app."""
        config = self._config(request, object_id)
        if not self.has_view_permission(request, config):
            raise PermissionDenied
        certificate = config.current_certificate
        if certificate is None:
            raise Http404("No certificate is installed.")
        der = x509.load_pem_x509_certificate(certificate.certificate_pem.encode("ascii")).public_bytes(Encoding.DER)
        response = HttpResponse(der, content_type="application/pkix-cert")
        response["Content-Disposition"] = f'attachment; filename="graph-{certificate.sha1_thumbprint}.cer"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def _config(self, request, object_id):
        config = self.get_object(request, unquote(object_id))
        if config is None:
            raise Http404("No Microsoft Graph config matches this ID.")
        return config

    def _certificate_config(self, request, object_id):
        if not request.user.is_superuser:
            raise PermissionDenied(SUPERUSER_ONLY)
        return self._config(request, object_id)

    def _page_context(self, request, config, title, **extra):
        return {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.opts,
            "original": config,
            "current": certificate_card(config.current_certificate),
            "previous": certificate_card(config.previous_certificate),
            "cancel_url": reverse(f"admin:{URL_NAME_PREFIX}_change", args=[config.pk]),
            **extra,
        }

    @staticmethod
    def _redirect_to_change(config):
        return HttpResponseRedirect(reverse(f"admin:{URL_NAME_PREFIX}_change", args=[config.pk]))

    @staticmethod
    def _report_removal(request, config, result, *, wanted_ses) -> None:
        messages.success(request, f"Removed {result.removed} Microsoft Graph certificate(s).")
        if result.provider_switched:
            messages.success(request, "Email delivery now uses AWS SES.")
            return
        email = EmailServiceConfig.load()
        if config.is_active and email.is_active and email.provider == EmailServiceConfig.Provider.GRAPH:
            messages.warning(request, (SES_NOT_READY if wanted_ses else "") + EMAIL_STOPPED)
