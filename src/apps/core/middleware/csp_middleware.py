import secrets

from django.conf import settings

from .csp_policy import CspPolicyMixin
from .csp_vendor_styles import VendorStyleNonceMixin


class ContentSecurityPolicyMiddleware(CspPolicyMixin, VendorStyleNonceMixin):
    """Add the configured CSP using the CMS iframe policy as its source of truth."""

    # The whole policy of a JSON response: it loads nothing.
    _JSON_POLICY = "default-src 'none'"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Make the nonce available before template rendering. Source-owned
        # templates opt in explicitly; the response rewriter below is limited
        # to two unavoidable styles from the upstream admin theme.
        request.csp_nonce = secrets.token_urlsafe(24)
        response = self.get_response(request)
        if "Content-Security-Policy" in response or "Content-Security-Policy-Report-Only" in response:
            return response

        report_only = getattr(settings, "CSP_REPORT_ONLY", True)
        header_name = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
        allow_framing = bool(getattr(response, "xframe_options_exempt", False))
        if self._is_json(response):
            # A page fetching JSON never applies the JSON's policy, so the full nonce-bearing policy (about
            # 1.3 KB, unique per response so HTTP/2 cannot index it) was often larger than the body. A short
            # static policy still locks the JSON down if it is ever opened as a document.
            response[header_name] = (
                self._JSON_POLICY if allow_framing else f"{self._JSON_POLICY}; frame-ancestors 'none'"
            )
            return response
        response[header_name] = self._build_policy(
            request.csp_nonce,
            allow_framing=allow_framing,
            form_action_origins=self._form_action_origins(response),
        )
        self._nonce_vendor_styles(response, request.csp_nonce)
        return response

    @staticmethod
    def _is_json(response) -> bool:
        content_type = response.get("Content-Type", "").split(";", 1)[0].strip().lower()
        return content_type == "application/json" or content_type.endswith("+json")
