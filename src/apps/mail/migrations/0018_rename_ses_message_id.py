from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0017_durable_campaign_delivery"),
    ]

    operations = [
        migrations.RenameField(
            model_name="recipientlog",
            old_name="ses_message_id",
            new_name="provider_message_id",
        ),
    ]
