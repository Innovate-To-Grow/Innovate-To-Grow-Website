"""Keep registration sheet dirty state in the same transaction as source edits, and the current-projects cache fresh."""

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    Event,
    EventRegistration,
    Question,
    RegistrationSheetSyncRecord,
    Ticket,
)
from apps.event.services.current_projects import CURRENT_PROJECTS_CACHE_KEY

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


def _clear_current_projects_cache():
    cache.delete(CURRENT_PROJECTS_CACHE_KEY)


def _belongs_to_active_schedule(project) -> bool:
    # The schedule sync hands update_or_create its schedule, so checking costs no query there.
    if CurrentProject._meta.get_field("schedule").is_cached(project):
        return bool(project.schedule and project.schedule.is_active)
    return CurrentProjectSchedule.objects.filter(pk=project.schedule_id, is_active=True).exists()


@receiver(post_save, sender=CurrentProject, dispatch_uid="event_current_project_saved")
@receiver(post_delete, sender=CurrentProject, dispatch_uid="event_current_project_deleted")
def current_project_changed(sender, instance, raw=False, **kwargs):
    # An admin edit (is_presenting is editable in the list) must not wait out the cache's timeout.
    if not raw and _belongs_to_active_schedule(instance):
        transaction.on_commit(_clear_current_projects_cache)


@receiver(post_save, sender=CurrentProjectSchedule, dispatch_uid="event_schedule_saved")
@receiver(post_delete, sender=CurrentProjectSchedule, dispatch_uid="event_schedule_deleted")
def schedule_changed(sender, instance, raw=False, **kwargs):
    # Renaming the live schedule or activating another one changes what /event/projects/ serves.
    if not raw:
        transaction.on_commit(_clear_current_projects_cache)
