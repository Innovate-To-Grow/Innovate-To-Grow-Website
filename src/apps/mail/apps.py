from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mail"
    label = "mail"
    verbose_name = "Mail"

    def ready(self):
        from django.contrib import admin

        register_background_jobs()
        register_sms_policy()

        from .admin.email_monitoring import get_email_monitoring_urls
        from .admin.inbox import get_inbox_urls
        from .admin.settings import get_mail_settings_urls

        # Guard against re-patching if ready() runs more than once (e.g. tests
        # using override_settings(INSTALLED_APPS=...) / modify_settings), which
        # would otherwise nest wrappers and duplicate the admin URLs.
        if not getattr(admin.AdminSite, "_mail_urls_patched", False):
            original_get_urls = admin.AdminSite.get_urls

            def patched_get_urls(site_self):
                return (
                    get_email_monitoring_urls()
                    + get_inbox_urls()
                    + get_mail_settings_urls()
                    + original_get_urls(site_self)
                )

            admin.AdminSite.get_urls = patched_get_urls
            admin.AdminSite._mail_urls_patched = True


def register_background_jobs():
    from apps.core.services.background_jobs import register_job_kind
    from apps.core.services.delivery_rates import Family, Lane

    dispatch = "apps.mail.services.campaign.dispatch"
    # Campaign recipients send on the bulk lane: claimed after every other job, and not at all while it is paced.
    for kind, handler, family in (
        ("mail.email_recipient", "send_email_recipient_job", Family.EMAIL),
        ("mail.sms_recipient", "send_sms_recipient_job", Family.SMS),
    ):
        register_job_kind(
            kind,
            handler=f"{dispatch}.{handler}",
            state_handler=f"{dispatch}.sync_delivery_job_state",
            stale_resolver=f"{dispatch}.resolve_stale_delivery_job",
            family=family,
            lane=Lane.BULK,
        )
    # A ticket text carries the registrant's ticket link: transactional, claimed before campaign jobs.
    register_job_kind(
        "mail.ticket_sms",
        handler="apps.mail.services.sms.ticket.send_ticket_sms_job",
        family=Family.SMS,
        lane=Lane.TRANSACTIONAL,
    )


def register_sms_policy():
    """Every SMS the site sends asks the SMS opt-out list first (core's send check), a new registration's first
    ticket may also go out as a text (the event app's ``initial_ticket_issued``), and saving SMS Settings drops the
    cached ``/register`` destination."""
    from django.db.models.signals import post_save

    from apps.event.signals import initial_ticket_issued
    from apps.mail.models import SmsConfig
    from apps.mail.services.sms import opt_outs, register_link, ticket

    opt_outs.register()
    initial_ticket_issued.connect(ticket.queue_ticket_sms, dispatch_uid="mail_queue_ticket_sms")
    post_save.connect(
        register_link.forget_register_destination, sender=SmsConfig, dispatch_uid="mail_forget_register_link"
    )
