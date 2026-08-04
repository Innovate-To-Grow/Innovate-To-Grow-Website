from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0016_delete_scamdetectorconfig"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailcampaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("queued", "Queued"),
                    ("sending", "Sending"),
                    ("partial", "Partially sent"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="recipientlog",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("retry", "Retry scheduled"),
                    ("sent", "Sent"),
                    ("delivered", "Delivered"),
                    ("bounced", "Bounced"),
                    ("complained", "Complained"),
                    ("rejected", "Rejected"),
                    ("failed", "Failed"),
                    ("uncertain", "Uncertain delivery"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="recipientlog",
            name="attempts",
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
        migrations.AddField(
            model_name="recipientlog",
            name="available_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recipientlog",
            name="claim_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="recipientlog",
            name="claimed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="recipientlog",
            name="uncertain_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="smscampaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("queued", "Queued"),
                    ("sending", "Sending"),
                    ("partial", "Partially sent"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="smsrecipientlog",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("retry", "Retry scheduled"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("uncertain", "Uncertain delivery"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="smsrecipientlog",
            name="attempts",
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
        migrations.AddField(
            model_name="smsrecipientlog",
            name="available_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="smsrecipientlog",
            name="claim_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="smsrecipientlog",
            name="claimed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="smsrecipientlog",
            name="uncertain_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
