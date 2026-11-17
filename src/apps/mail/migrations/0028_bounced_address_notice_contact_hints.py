"""Keep unverified contact name and phone hints from the latest left-organisation notice."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mail", "0027_bounced_address_left_org")]

    operations = [
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_contact_name",
            field=models.CharField(
                blank=True, db_default="", default="", help_text="Unverified name in the latest notice.", max_length=100
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_contact_phone",
            field=models.CharField(
                blank=True, db_default="", default="", help_text="Unverified phone in the latest notice.", max_length=40
            ),
        ),
    ]
