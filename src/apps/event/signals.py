"""Keep registration sheet dirty state in the same transaction as source edits."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.event.models import Event, EventRegistration, Question, RegistrationSheetSyncRecord, Ticket

EVENT_AUDIT_FIELDS = {
    "registration_sheet_synced_at",
    "registration_sheet_sync_count",
    "registration_sheet_sync_error",
    "updated_at",
}
REGISTRATION_AUDIT_FIELDS = {"ticket_email_sent_at", "ticket_email_error", "updated_at"}


def _schedule(event):
    from apps.event.services.registration_sheet_sync import schedule_registration_sync

    schedule_registration_sync(event)


@receiver(post_save, sender=Event, dispatch_uid="event_registration_sheet_event_saved")
def event_saved(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or (update_fields is not None and set(update_fields) <= EVENT_AUDIT_FIELDS):
        return
    _schedule(instance)


@receiver(post_save, sender=EventRegistration, dispatch_uid="event_registration_sheet_registration_saved")
def registration_saved(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or (update_fields is not None and set(update_fields) <= REGISTRATION_AUDIT_FIELDS):
        return
    event = Event.objects.filter(pk=instance.event_id).first()
    if event is not None:
        _schedule(event)


@receiver(post_delete, sender=EventRegistration, dispatch_uid="event_registration_sheet_registration_deleted")
def registration_deleted(sender, instance, origin=None, **kwargs):
    # Event cascade deletion also removes the configuration and remote mapping;
    # creating jobs while deleting that parent would be both invalid and useless.
    if isinstance(origin, Event) or getattr(origin, "model", None) is Event:
        return
    event = Event.objects.filter(pk=instance.event_id).first()
    if event is None or not event.registration_sheet_id:
        return
    record, _ = RegistrationSheetSyncRecord.objects.get_or_create(event=event, registration_id=instance.pk)
    record.deleted_at = timezone.now()
    record.save(update_fields=["deleted_at", "updated_at"])
    _schedule(event)


@receiver(post_save, sender=Question, dispatch_uid="event_registration_sheet_question_saved")
@receiver(post_save, sender=Ticket, dispatch_uid="event_registration_sheet_ticket_saved")
def related_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        event = Event.objects.filter(pk=instance.event_id).first()
        if event is not None:
            _schedule(event)


@receiver(post_delete, sender=Question, dispatch_uid="event_registration_sheet_question_deleted")
@receiver(post_delete, sender=Ticket, dispatch_uid="event_registration_sheet_ticket_deleted")
def related_deleted(sender, instance, origin=None, **kwargs):
    if isinstance(origin, Event) or getattr(origin, "model", None) is Event:
        return
    event = Event.objects.filter(pk=instance.event_id).first()
    if event is not None:
        _schedule(event)
