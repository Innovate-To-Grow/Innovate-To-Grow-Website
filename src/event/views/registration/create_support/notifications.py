from event.services.registration_sheet_sync import schedule_registration_sync


def send_initial_ticket_email(registration) -> None:
    import event.views.registration as registration_api

    schedule_registration_sync(registration.event)
    try:
        from event.services.ticket_mail import send_ticket_email

        send_ticket_email(registration)
    except Exception:
        registration_api.logger.warning(
            "Failed to send initial ticket email",
            exc_info=True,
        )
