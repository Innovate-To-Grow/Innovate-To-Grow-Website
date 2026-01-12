"""
Event Registration model for linking Members to Events.
"""

from django.db import models


class EventRegistration(models.Model):
    """
    Links a Member to an Event, representing that the member has registered for the event.
    """
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='registrations',
        help_text="The event this registration is for",
        verbose_name="Event"
    )

    member = models.ForeignKey(
        'authn.Member',
        on_delete=models.CASCADE,
        related_name='event_registrations',
        help_text="The member who registered",
        verbose_name="Member"
    )

    registered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the member registered for this event",
        verbose_name="Registered At"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this registration was last updated",
        verbose_name="Updated At"
    )

    class Meta:
        verbose_name = "Event Registration"
        verbose_name_plural = "Event Registrations"
        ordering = ['-registered_at']
        unique_together = [['event', 'member']]
        indexes = [
            models.Index(fields=['event']),
            models.Index(fields=['member']),
            models.Index(fields=['registered_at']),
        ]

    def __str__(self):
        return f"{self.member.get_full_name() or self.member.username} - {self.event.event_name}"
