"""Reclassify retained zero-size receiving limits without rebuilding unrelated address history."""

from django.db import migrations, models

from ._zero_limits import reconcile


def reclassify_zero_limits(apps, schema_editor):
    reconcile(apps, schema_editor.connection.alias)


def restore_zero_limits(apps, schema_editor):
    reconcile(apps, schema_editor.connection.alias, reverse=True)


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0028_bounced_address_notice_contact_hints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bouncedaddress",
            name="suggestion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("unsubscribe", "Unsubscribe: they reported us as spam"),
                    ("undeliverable", "Mark undeliverable or replace the address"),
                    (
                        "replace",
                        "Replace the address (the mailbox is disabled), or mark it undeliverable",
                    ),
                    (
                        "consider",
                        "Repeated temporary failures: check the receiving service, then retry this address",
                    ),
                    (
                        "relay",
                        "Our sending side: relay denied. Check our sending route and authorisation, then retry from another configured sender; the problem is not the address",
                    ),
                    (
                        "reputation",
                        "Our sending side: spam or reputation rejection. Check reputation, authentication and content, then retry from another configured sender; the problem is not the address",
                    ),
                    (
                        "policy",
                        "Their server's policy refused the message, not the address: no action",
                    ),
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
        migrations.RunPython(reclassify_zero_limits, restore_zero_limits),
    ]
