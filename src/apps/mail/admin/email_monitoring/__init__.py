"""Mail → Delivery Operations → Email Monitoring (admin URLs; the views are in ``views``, ``addresses`` and
``address_actions``)."""

from django.contrib import admin
from django.urls import path

from . import address_actions, addresses, views


def get_email_monitoring_urls():
    view = admin.site.admin_view
    return [
        path("mail/email-monitoring/", view(views.overview_view), name="mail_email_monitoring"),
        path("mail/email-monitoring/data/", view(views.overview_data_view), name="mail_email_monitoring_data"),
        path("mail/email-monitoring/emails/", view(views.email_log_view), name="mail_email_monitoring_emails"),
        path(
            "mail/email-monitoring/emails/<uuid:pk>/",
            view(views.email_detail_view),
            name="mail_email_monitoring_email",
        ),
        path("mail/email-monitoring/bounces/", view(views.bounce_list_view), name="mail_email_monitoring_bounces"),
        path(
            "mail/email-monitoring/campaigns/<uuid:pk>/",
            view(views.campaign_view),
            name="mail_email_monitoring_campaign",
        ),
        path(
            "mail/email-monitoring/bounce-processing/",
            view(views.bounce_processing_view),
            name="mail_email_monitoring_bounce_processing",
        ),
    ] + _address_urls(view)


def _address_urls(view):
    """Email Monitoring → Bounced addresses (``addresses`` and ``address_actions``)."""
    return [
        path(
            "mail/email-monitoring/addresses/",
            view(addresses.address_list_view),
            name="mail_email_monitoring_addresses",
        ),
        path(
            "mail/email-monitoring/addresses/export/",
            view(addresses.addresses_export_view),
            name="mail_email_monitoring_addresses_export",
        ),
        path(
            "mail/email-monitoring/addresses/bulk/",
            view(address_actions.addresses_bulk_view),
            name="mail_email_monitoring_addresses_bulk",
        ),
        path(
            "mail/email-monitoring/addresses/rebuild/",
            view(address_actions.addresses_rebuild_view),
            name="mail_email_monitoring_addresses_rebuild",
        ),
        path(
            "mail/email-monitoring/addresses/<uuid:pk>/",
            view(addresses.address_detail_view),
            name="mail_email_monitoring_address",
        ),
        path(
            "mail/email-monitoring/addresses/<uuid:pk>/<slug:action>/",
            view(address_actions.address_action_view),
            name="mail_email_monitoring_address_action",
        ),
    ]
