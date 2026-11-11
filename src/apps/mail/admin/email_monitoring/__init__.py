"""Mail → Delivery Operations → Email Monitoring (admin URLs; the views are in ``views``)."""

from django.contrib import admin
from django.urls import path

from . import views


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
    ]
