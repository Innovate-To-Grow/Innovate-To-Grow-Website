import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_intelligence", "0006_public_assistant_input_limits"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicAssistantTokenBudget",
            fields=[
                (
                    "ip_hash",
                    models.CharField(
                        help_text="Salted SHA-256 hash of the visitor IP (never the raw IP).",
                        max_length=64,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("window_id", models.PositiveBigIntegerField(default=0)),
                ("tokens_used", models.PositiveBigIntegerField(default=0)),
                ("window_expires_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "verbose_name": "Public Assistant Token Budget",
                "verbose_name_plural": "Public Assistant Token Budgets",
            },
        ),
        migrations.CreateModel(
            name="PublicAssistantTokenReservation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("window_id", models.PositiveBigIntegerField()),
                ("reserved_tokens", models.PositiveBigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservations",
                        to="system_intelligence.publicassistanttokenbudget",
                    ),
                ),
            ],
            options={
                "verbose_name": "Public Assistant Token Reservation",
                "verbose_name_plural": "Public Assistant Token Reservations",
            },
        ),
    ]
