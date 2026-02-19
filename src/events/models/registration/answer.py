"""Event registration answer model."""

from django.db import models

from core.models.base.control import ProjectControlModel


class EventRegistrationAnswer(ProjectControlModel):
    """Answer rows for event registration questions."""

    registration = models.ForeignKey(
        "events.EventRegistration",
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        "events.EventQuestion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answers",
    )
    question_prompt = models.CharField(max_length=500)
    answer_text = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["registration", "question_prompt"]]
        indexes = [
            models.Index(fields=["registration", "order"]),
        ]

    def __str__(self):
        return f"{self.registration_id} - {self.question_prompt[:60]}"
