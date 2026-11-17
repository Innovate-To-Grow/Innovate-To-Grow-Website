"""Persist one-address retry provenance, method snapshots and exact per-campaign bounce evidence.

The conditional source/address constraint is the database-level idempotency guard for concurrent retry POSTs.
Existing Graph campaign links are backfilled only from retained reports that name the campaign exactly; likely
matches never become retry evidence, including links whose aggregate match label was later upgraded to exact.

Reversing is refused while retry rows exist: dropping their provenance would turn them into ordinary editable
Manual Emails campaigns under the preceding schema.
"""

from collections import defaultdict
from email.utils import parseaddr

import django.db.models.deletion
from django.db import migrations, models


def backfill_exact_graph_categories(apps, schema_editor):
    db = schema_editor.connection.alias
    Address = apps.get_model("mail", "BouncedAddress")
    Link = apps.get_model("mail", "BouncedAddressCampaign")
    Bounce = apps.get_model("core", "EmailBounce")

    address_ids = {
        address.lower(): pk for pk, address in Address.objects.using(db).values_list("pk", "address").iterator()
    }
    counts = defaultdict(lambda: defaultdict(int))
    reports = (
        Bounce.objects.using(db)
        .filter(campaign_id__isnull=False)
        .exclude(match_method="unmatched")
        .values_list("campaign_id", "recipient", "category")
    )
    for campaign_id, raw_address, category in reports.iterator(chunk_size=1000):
        _name, parsed = parseaddr(raw_address or "")
        address_id = address_ids.get(parsed.strip().lower())
        if address_id is not None and category:
            counts[(address_id, campaign_id)][category] += 1

    changed = []
    links = Link.objects.using(db).filter(source="graph")
    for link in links.iterator(chunk_size=1000):
        exact_counts = counts.get((link.bounced_address_id, link.campaign_id))
        if not exact_counts:
            continue
        link.graph_category_counts = dict(exact_counts)
        link.match = "exact"
        changed.append(link)
        if len(changed) >= 1000:
            Link.objects.using(db).bulk_update(changed, ["graph_category_counts", "match"])
            changed.clear()
    if changed:
        Link.objects.using(db).bulk_update(changed, ["graph_category_counts", "match"])


def prevent_unsafe_reverse(apps, schema_editor):
    """Do not erase the safety identity of a still-existing retry campaign."""
    Campaign = apps.get_model("mail", "EmailCampaign")
    if Campaign.objects.using(schema_editor.connection.alias).filter(retry_source_campaign__isnull=False).exists():
        raise RuntimeError(
            "Cannot reverse mail.0031 while retry campaigns exist; resolve them under an approved rollback procedure."
        )


class Migration(migrations.Migration):
    dependencies = [("mail", "0030_bouncedaddress_hint_retention")]

    operations = [
        migrations.AddField(
            model_name="bouncedaddresscampaign",
            name="graph_category_counts",
            field=models.JSONField(
                blank=True,
                db_default={},
                default=dict,
                help_text="Exact-match Graph bounce categories recorded for this campaign/address pair.",
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_address",
            field=models.CharField(blank=True, db_default="", default="", editable=False, max_length=254),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_configuration_set",
            field=models.CharField(blank=True, db_default="", default="", editable=False, max_length=255),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_from_email",
            field=models.CharField(blank=True, db_default="", default="", editable=False, max_length=254),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_from_name",
            field=models.CharField(blank=True, db_default="", default="", editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_sending_provider",
            field=models.CharField(blank=True, db_default="", default="", editable=False, max_length=16),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_email_config",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="email_retry_drafts",
                to="core.emailserviceconfig",
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="retry_source_campaign",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="retry_drafts",
                to="mail.emailcampaign",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.UniqueConstraint(
                condition=models.Q(("retry_source_campaign__isnull", False)),
                fields=("retry_source_campaign", "retry_address"),
                name="unique_email_retry_source_address",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailcampaign",
            constraint=models.CheckConstraint(
                condition=models.Q(("retry_source_campaign__isnull", True))
                | (
                    models.Q(
                        ("audience_type", "manual"),
                        ("event__isnull", True),
                        ("exclude_audience_type", ""),
                        ("exclude_event__isnull", True),
                        ("exclude_ticket_id", ""),
                        ("retry_email_config__isnull", False),
                    )
                    & models.Q(("manual_emails", models.F("retry_address")))
                    & ~models.Q(("retry_address", ""))
                    & ~models.Q(("retry_sending_provider", ""))
                    & ~models.Q(("retry_from_email", ""))
                    & ~models.Q(("retry_source_campaign", models.F("id")))
                ),
                name="email_retry_locked_shape",
            ),
        ),
        migrations.RunPython(backfill_exact_graph_categories, prevent_unsafe_reverse),
    ]
