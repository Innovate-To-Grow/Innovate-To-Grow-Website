from django.db import models

from core.models import ProjectControlModel


class EventScheduleSection(ProjectControlModel):
    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="schedule_sections")
    code = models.CharField(max_length=32)
    label = models.CharField(max_length=255)
    display_order = models.PositiveIntegerField(default=0)
    start_time = models.CharField(max_length=10, default="1:00")
    slot_minutes = models.PositiveIntegerField(default=30)
    accent_color = models.CharField(max_length=20, blank=True, default="#002856")

    class Meta:
        ordering = ["display_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["event", "code"], name="unique_schedule_section_per_event"),
        ]

    def __str__(self):
        return f"{self.event.name} - {self.code}"


class EventScheduleTrack(ProjectControlModel):
    section = models.ForeignKey("event.EventScheduleSection", on_delete=models.CASCADE, related_name="tracks")
    track_number = models.PositiveIntegerField()
    label = models.CharField(max_length=255, blank=True, default="")
    room = models.CharField(max_length=255, blank=True, default="")
    zoom_link = models.CharField(max_length=500, blank=True, default="")
    topic = models.CharField(max_length=255, blank=True, default="")
    winner = models.CharField(max_length=255, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["section__display_order", "display_order", "track_number"]
        constraints = [
            models.UniqueConstraint(fields=["section", "track_number"], name="unique_track_number_per_section"),
            models.UniqueConstraint(fields=["section", "display_order"], name="unique_track_order_per_section"),
        ]

    def __str__(self):
        return f"{self.section.event.name} - Track {self.track_number}"


class EventScheduleSlot(ProjectControlModel):
    track = models.ForeignKey("event.EventScheduleTrack", on_delete=models.CASCADE, related_name="slots")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_schedule_slots",
    )
    slot_order = models.PositiveIntegerField()
    is_break = models.BooleanField(default=False)
    year_semester = models.CharField(max_length=50, blank=True, default="")
    class_code = models.CharField(max_length=32, blank=True, default="")
    team_number = models.CharField(max_length=32, blank=True, default="")
    team_name = models.CharField(max_length=255, blank=True, default="")
    project_title = models.CharField(max_length=500, blank=True, default="")
    organization = models.CharField(max_length=255, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="")
    abstract = models.TextField(blank=True, default="")
    student_names = models.TextField(blank=True, default="")
    name_title = models.CharField(max_length=500, blank=True, default="")
    display_text = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["track__section__display_order", "track__display_order", "slot_order"]
        constraints = [
            models.UniqueConstraint(fields=["track", "slot_order"], name="unique_slot_order_per_track"),
        ]

    def __str__(self):
        return f"{self.track} - Slot {self.slot_order}"


class EventAgendaItem(ProjectControlModel):
    class SectionType(models.TextChoices):
        EXPO = "expo", "Expo"
        AWARDS = "awards", "Awards & Reception"

    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="agenda_items")
    section_type = models.CharField(max_length=20, choices=SectionType.choices)
    time_label = models.CharField(max_length=20)
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["section_type", "display_order", "time_label"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "section_type", "display_order"],
                name="unique_agenda_order_per_event_section",
            ),
        ]

    def __str__(self):
        return f"{self.event.name} - {self.title}"
