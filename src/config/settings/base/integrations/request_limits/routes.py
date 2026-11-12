"""
Which scope each route belongs to, and the routes that are never limited.

Keys are a route's ``view_name`` as Django resolves it (``"namespace:name"``, or the bare name in the root URLconf)
or the dotted path of its view. A value is a scope, or ``{"METHOD": scope, "*": scope}`` when methods differ.

The site's own views name their scope themselves with a ``rate_limit_scope`` attribute (same value forms) or
``rate_limit_exempt = "reason"``, so this table holds only what cannot carry an attribute: Django-admin routes and
third-party views (an app can also register those from ``AppConfig.ready()`` with
``apps.core.services.request_limits.register_scope``). The table takes precedence over both, so a
``REQUEST_RATE_LIMITS_OVERRIDES`` entry can move any route, the site's own views included. Everything else falls back by path, method and sign-in: ``/admin-api/`` is ``cli``,
``/admin/`` is ``staff-admin``, a GET is ``public-read`` or ``member-read``, other methods ``public-write`` or
``member-write``. So no route is ever unlimited by accident, and ``apps.core.tests.request_limits.test_coverage``
fails when a key here matches no route.
"""

ROUTES = {
    # --- P2: admin polling (every 1-2 s while a page is open) ------------------------------------------------------
    "admin:mail_emailcampaign_send_status_json": "staff-polling",
    "admin:mail_smscampaign_send_status_json": "staff-polling",
    "admin:mail_delivery_rates_status": "staff-polling",
    "admin:core_request_limits_status": "staff-polling",
    "admin:mail_delivery_dashboard_data": "staff-polling",
    "admin:mail_email_monitoring_data": "staff-polling",
    "admin:system_intelligence_usage_data": "staff-polling",
    "admin:jsi18n": "staff-polling",
    # --- P3: admin heavy, bulk, AI, external calls -----------------------------------------------------------------
    "admin:system_intelligence_send": "staff-bulk",
    "admin:system_intelligence_command": "staff-bulk",
    "admin:system_intelligence_export_download": "staff-bulk",
    "admin:search": "staff-bulk",
    "admin:authn_member_import_excel": "staff-bulk",
    "admin:authn_member_import_confirm": "staff-bulk",
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
    "admin:helpdesk_ticket_attachment": "staff-bulk",
    # Email Monitoring → Bounced addresses: the action POSTs, bulk actions, the counts rebuild and the export.
    "admin:mail_email_monitoring_address_action": "staff-bulk",
    "admin:mail_email_monitoring_addresses_bulk": "staff-bulk",
    "admin:mail_email_monitoring_addresses_rebuild": "staff-bulk",
    "admin:mail_email_monitoring_addresses_export": "staff-bulk",
    # Third party (django-ckeditor-5).
    "ck_editor_5_upload_file": "staff-bulk",
}

# Never limited, each with its reason, for routes whose view cannot say so itself (the site's own views set
# ``rate_limit_exempt``). The health probes (/livez/, /readyz/, /health/) are answered by HealthCheckMiddleware before
# this middleware runs, and CORS preflights (OPTIONS) are never limited.
EXEMPT = {
    "projects:projects-current-redirect": "A redirect with no work behind it.",
    "django.views.static.serve": "Development-only file serving (DEBUG); production serves files from S3.",
    "django.contrib.staticfiles.views.serve": "Development-only static files (DEBUG).",
}
