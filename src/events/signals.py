"""
Signals for keeping Event.updated_at in sync with child model changes.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Event, Presentation, Program, SpecialAward, Track, TrackWinner


def _touch_event(event_id):
    """Update event watermark timestamp for downstream delta sync."""
    if not event_id:
        return
    Event.objects.filter(pk=event_id).update(updated_at=timezone.now())


def _event_id_from_track(track_id):
    return Track.objects.filter(pk=track_id).values_list("program__event_id", flat=True).first()


def _event_id_from_program(program_id):
    return Program.objects.filter(pk=program_id).values_list("event_id", flat=True).first()


@receiver(post_save, sender=Program)
@receiver(post_delete, sender=Program)
def touch_event_for_program(sender, instance, **kwargs):
    _touch_event(instance.event_id)


@receiver(post_save, sender=Track)
@receiver(post_delete, sender=Track)
def touch_event_for_track(sender, instance, **kwargs):
    event_id = _event_id_from_track(instance.id)
    if event_id is None:
        event_id = _event_id_from_program(instance.program_id)
    _touch_event(event_id)


@receiver(post_save, sender=Presentation)
@receiver(post_delete, sender=Presentation)
def touch_event_for_presentation(sender, instance, **kwargs):
    _touch_event(_event_id_from_track(instance.track_id))


@receiver(post_save, sender=TrackWinner)
@receiver(post_delete, sender=TrackWinner)
def touch_event_for_track_winner(sender, instance, **kwargs):
    _touch_event(instance.event_id)


@receiver(post_save, sender=SpecialAward)
@receiver(post_delete, sender=SpecialAward)
def touch_event_for_special_award(sender, instance, **kwargs):
    _touch_event(instance.event_id)
