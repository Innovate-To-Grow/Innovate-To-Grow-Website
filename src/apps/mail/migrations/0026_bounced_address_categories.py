"""Bounced addresses by bounce category.

Adds ``BouncedAddress.category_counts`` (Microsoft Graph reports per category) and ``last_category`` (with database
defaults, so the release before this one can keep saving while a deploy rolls out), and the new suggestions: replace
the address (disabled mailbox), relay denied and spam or reputation rejection (our sending side).

When Graph reports have been counted already, it **parks** the Graph counting cursor far in the future: the previous
release, still running until the deploy finishes, then counts no Graph report (no report is past the cursor), and the
first Graph count by the new release (the Bounced addresses page or the worker's hourly maintenance) starts the Graph
counts again from the stored reports, which ``core.0047`` has categorised, and records it like a rebuild. SES counts,
review state, suppressions and the action log stay. Every stored report is younger than the 365-day retention, so
nothing is lost. The reverse unparks the cursor with the Graph counts zeroed (the previous release counts them again
from the stored reports) and removes the new suggestions (the hourly refresh suggests again).
"""

import uuid
from datetime import UTC, datetime

from django.db import migrations, models

# The same values as ``aggregate.PARKED`` and ``aggregate.PARKED_ID`` (the cursor query compares ids too).
PARKED = datetime(9999, 12, 31, tzinfo=UTC)
PARKED_ID = uuid.UUID(int=2**128 - 1)
GRAPH_COUNTS = ("hard_count", "soft_count", "rejected_count", "delayed_count", "unknown_count", "matched_count")
GRAPH_TEXTS = ("last_classification", "last_status_code", "last_reason", "last_diagnostic", "last_remote_mta")


def park_graph_counting(apps, schema_editor):
    State = apps.get_model("mail", "BounceAggregationState")
    State.objects.filter(source="graph", processed_total__gt=0).update(cursor_at=PARKED, cursor_id=PARKED_ID)


def unpark_graph_counting(apps, schema_editor):
    State = apps.get_model("mail", "BounceAggregationState")
    BouncedAddress = apps.get_model("mail", "BouncedAddress")
    if State.objects.filter(source="graph", cursor_at__gte=PARKED).update(
        cursor_at=None, cursor_id=None, processed_total=0
    ):
        apps.get_model("mail", "BouncedAddressCampaign").objects.filter(source="graph").delete()
        BouncedAddress.objects.filter(graph_last_at__isnull=False).update(
            **dict.fromkeys(GRAPH_COUNTS, 0),
            **dict.fromkeys(GRAPH_TEXTS, ""),
            graph_first_at=None,
            graph_last_at=None,
            first_bounce_at=models.F("ses_first_at"),
            last_bounce_at=models.F("ses_last_at"),
            suggestion="",
        )
    BouncedAddress.objects.filter(suggestion__in=("replace", "relay", "reputation")).update(suggestion="")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_email_bounce_category"),
        ("mail", "0025_sms_link_revocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="bouncedaddress",
            name="category_counts",
            field=models.JSONField(
                blank=True,
                db_default={},
                default=dict,
                help_text="Microsoft Graph reports by category (what went wrong), each counted once.",
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="last_category",
            field=models.CharField(blank=True, db_default="", default="", max_length=24),
        ),
        migrations.AlterField(
            model_name="bouncedaddress",
            name="suggestion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("unsubscribe", "Unsubscribe: they reported us as spam"),
                    ("undeliverable", "Mark undeliverable or replace the address"),
                    ("replace", "Replace the address (the mailbox is disabled), or mark it undeliverable"),
                    ("consider", "Consider marking undeliverable (repeated temporary failures)"),
                    (
                        "relay",
                        "Our sending side: relay denied. Check our sending route and authorisation, not the address",
                    ),
                    (
                        "reputation",
                        "Our sending side: spam or reputation rejection. Check reputation, authentication and content, "
                        "not the address",
                    ),
                    ("policy", "Their server's policy refused the message, not the address: no action"),
                ],
                db_index=True,
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(park_graph_counting, unpark_graph_counting),
    ]
