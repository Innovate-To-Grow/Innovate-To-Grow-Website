"""Bounced addresses: left-the-organisation notices.

Adds the counts of the helpdesk's "left the organisation" automatic replies that answer an email the site sent
(``left_org_count``, the first and latest, the address the latest one names instead and its helpdesk ticket), with
database defaults so the previous release can keep saving rows while a deploy rolls out, and the suggestion "May have
left". Nothing is backfilled: the helpdesk records the email a notice answers from this release on, so counting starts
with the notices imported after the deploy. The reverse clears that suggestion (the hourly refresh suggests again) and
the notices' counting cursor, so applying it again counts the notices still in the inbound queue again.
"""

from django.db import migrations, models


def forget_notices(apps, schema_editor):
    apps.get_model("mail", "BouncedAddress").objects.filter(suggestion="left_org").update(suggestion="")
    apps.get_model("mail", "BounceAggregationState").objects.filter(source="inbound").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0026_bounced_address_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_contact",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="The address the latest notice names instead (a hint from its text: never verified).",
                max_length=254,
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_contact_kind",
            field=models.CharField(blank=True, db_default="", default="", max_length=16),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_count",
            field=models.PositiveIntegerField(
                db_default=0,
                default=0,
                help_text="Automatic replies to the site's mail saying the person left or the address changed.",
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_first_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_last_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_ticket",
            field=models.PositiveIntegerField(
                blank=True, help_text="The helpdesk ticket that holds the latest notice.", null=True
            ),
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
                        "Our sending side: spam or reputation rejection. Check reputation, authentication and content, not the address",
                    ),
                    ("policy", "Their server's policy refused the message, not the address: no action"),
                    (
                        "left_org",
                        "May have left: an automatic reply says so. Check the notice, then replace the address or mark it undeliverable",
                    ),
                ],
                db_index=True,
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, forget_notices),
    ]
