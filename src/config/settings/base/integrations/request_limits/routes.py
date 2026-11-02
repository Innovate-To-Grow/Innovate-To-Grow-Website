"""
Which scope each route belongs to, and the routes that are never limited.

Keys are a route's ``view_name`` as Django resolves it (``"namespace:name"``, or the bare name in the root URLconf)
or the dotted path of its view. A value is a scope, or ``{"METHOD": scope, "*": scope}`` when methods differ.

A view can name its scope itself with a ``rate_limit_scope`` attribute (same value forms), and an app can register
third-party views from ``AppConfig.ready()`` with ``apps.core.services.request_limits.register_scope``; both take
precedence over this table. Everything else falls back by path, method and sign-in: ``/admin-api/`` is ``cli``,
``/admin/`` is ``staff-admin``, a GET is ``public-read`` or ``member-read``, other methods ``public-write`` or
``member-write``. So no route is ever unlimited by accident, and ``apps.core.tests.request_limits.test_coverage``
fails when a key here matches no route.
"""

ROUTES = {
    # --- P0: sign-in and verification a person started -----------------------------------------------------------
    "admin-login": {"GET": "staff-admin", "*": "auth-sign-in"},
    "admin-send-verification-challenge": "auth-challenge",
    "maintenance-bypass": "auth-sign-in",
    "authn:login": "auth-sign-in",
    "authn:change-password": "auth-sign-in",
    "authn:accept-invitation": {"GET": "tokenized-link", "*": "auth-sign-in"},
    "cli_admin:oauth-token": "auth-sign-in",
    "authn:public-key": "auth-challenge",
    "authn:send-verification-challenge": "auth-challenge",
    "authn:send-verification-request-status": "auth-challenge",
    "authn:email-auth-request-code": "auth-code-send",
    "authn:phone-auth-request-code": "auth-code-send",
    "authn:register": "auth-code-send",
    "authn:register-resend-code": "auth-code-send",
    "authn:login-request-code": "auth-code-send",
    "authn:password-reset-request-code": "auth-code-send",
    "authn:change-password-request-code": "auth-code-send",
    "authn:delete-account-request-code": "auth-code-send",
    "authn:contact-email-request-verification": "auth-code-send",
    "authn:contact-phone-request-verification": "auth-code-send",
    "event:send-phone-code": "auth-code-send",
    "event:send-secondary-email-code": "auth-code-send",
    "authn:email-auth-verify-code": "auth-code-verify",
    "authn:phone-auth-verify-code": "auth-code-verify",
    "authn:register-verify-code": "auth-code-verify",
    "authn:login-verify-code": "auth-code-verify",
    "authn:password-reset-verify-code": "auth-code-verify",
    "authn:password-reset-confirm": "auth-code-verify",
    "authn:change-password-verify-code": "auth-code-verify",
    "authn:change-password-confirm": "auth-code-verify",
    "authn:delete-account-verify-code": "auth-code-verify",
    "authn:delete-account-confirm": "auth-code-verify",
    "authn:contact-email-verify-code": "auth-code-verify",
    "authn:contact-phone-verify-code": "auth-code-verify",
    "event:verify-phone-code": "auth-code-verify",
    "event:verify-secondary-email-code": "auth-code-verify",
    "mail:login-link": "auth-email-link",
    "mail:magic-login": "auth-email-link",
    "authn:impersonate-login": "auth-email-link",
    "legacy_view:exchange": "auth-email-link",
    "authn:token-refresh": "auth-token-refresh",
    "authn:session": "auth-session",
    "event:checkin-scan": "checkin-scan",
    "event:checkin-undo": "checkin-scan",
    "mail:ses-events": "webhook-ses",
    # --- P1: what a person waits for on screen -------------------------------------------------------------------
    "authn:logout": "member-write",
    "event:registration-create": "member-send",
    "event:resend-ticket-email": "member-send",
    "mail:resubscribe": "tokenized-link",
    "cms-preview-fetch": "tokenized-link",
    "cli_admin:oauth-authorize": "cli",
    "legacy_view:root": "legacy-proxy",
    "legacy_view:proxy": "legacy-proxy",
    # --- P2: automatic and repeating requests --------------------------------------------------------------------
    "csp-report": "telemetry",
    "analytics:pageview-create": "telemetry",
    "sitemap-xml": "public-background",
    "cms-embed-hosts": "public-background",
    "system_intelligence:public-assistant-config": "public-background",
    "cms-live-preview": "staff-polling",
    "event:checkin-status": "checkin-status",
    "admin:mail_emailcampaign_send_status_json": "staff-polling",
    "admin:mail_smscampaign_send_status_json": "staff-polling",
    "admin:mail_delivery_rates_status": "staff-polling",
    "admin:mail_delivery_dashboard_data": "staff-polling",
    "admin:system_intelligence_usage_data": "staff-polling",
    "admin:jsi18n": "staff-polling",
    # --- P3: heavy, bulk, AI ---------------------------------------------------------------------------------------
    "projects:projects-all": "public-heavy",
    "projects:projects-past-all": "public-heavy",
    "projects:projects-past-ai-search": "ai",
    "system_intelligence:public-assistant-chat": "ai",
    "admin:system_intelligence_send": "staff-bulk",
    "admin:system_intelligence_command": "staff-bulk",
    "admin:system_intelligence_export_download": "staff-bulk",
    "admin:search": "staff-bulk",
    "admin:authn_member_import_excel": "staff-bulk",
    "admin:authn_member_export_excel": "staff-bulk",
    "admin:cms_cmspage_import": "staff-bulk",
    "admin:cms_cmspage_export": "staff-bulk",
    "admin:cms_cmspage_asset_upload": "staff-bulk",
    "admin:cms_newsfeedsource_sync_all_feeds": "staff-bulk",
    "admin:cms_pageview_ip_geo_lookup": "staff-bulk",
    "admin:event_checkin_export": "staff-bulk",
    "admin:event_currentprojectschedule_pull": "staff-bulk",
    "admin:event_eventregistration_send_all_ticket_emails": "staff-bulk",
    "admin:projects_pastprojectssheetconfig_pull": "staff-bulk",
    "admin:projects_import_csv": "staff-bulk",
    "admin:projects_publish_all": "staff-bulk",
    "admin:mail_emailcampaign_send_confirm": "staff-bulk",
    "admin:mail_smscampaign_send_confirm": "staff-bulk",
    "ck_editor_5_upload_file": "staff-bulk",
}

# Never limited, each with its reason. The health probes (/livez/, /readyz/, /health/) are answered by
# HealthCheckMiddleware before this middleware runs, and CORS preflights (OPTIONS) are never limited.
EXEMPT = {
    "robots-txt": "A static text file crawlers fetch; refusing it would only make them guess.",
    "layout-theme": "Render-blocking stylesheet on every page and cached by the CDN; a refusal unstyles the site.",
    "mail:oneclick-unsubscribe": "Legal one-click opt-out (RFC 8058); an unsubscribe must never be refused.",
    "projects:projects-current-redirect": "A redirect with no work behind it.",
    "django.views.static.serve": "Development-only file serving (DEBUG); production serves files from S3.",
    "django.contrib.staticfiles.views.serve": "Development-only static files (DEBUG).",
}
