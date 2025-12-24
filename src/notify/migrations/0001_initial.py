from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], help_text="Notification channel (email or SMS).", max_length=10)),
                ("target", models.CharField(help_text="Email address or phone number notified.", max_length=255)),
                ("subject", models.CharField(blank=True, help_text="Subject for email notifications.", max_length=255)),
                ("message", models.TextField(help_text="Notification body content.")),
                ("provider", models.CharField(default="console", help_text="Provider used to send the notification.", max_length=64)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")], default="pending", help_text="Delivery status.", max_length=10)),
                ("error_message", models.TextField(blank=True, help_text="Error details if delivery failed.")),
                ("sent_at", models.DateTimeField(blank=True, help_text="When the notification was sent.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="When the notification log was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="When the notification log was last updated.")),
            ],
            options={
                "verbose_name": "Notification Log",
                "verbose_name_plural": "Notification Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="VerificationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], help_text="Verification channel (email or SMS).", max_length=10)),
                ("method", models.CharField(choices=[("code", "Code"), ("link", "Link")], help_text="Verification delivery method (code or link).", max_length=10)),
                ("target", models.CharField(help_text="Email address or phone number to verify.", max_length=255)),
                ("purpose", models.CharField(default="contact_verification", help_text="Purpose of the verification (e.g., contact_verification).", max_length=64)),
                ("code", models.CharField(blank=True, help_text="Verification code when method is code.", max_length=12, null=True)),
                ("token", models.CharField(blank=True, db_index=True, help_text="Verification token when method is link.", max_length=64, null=True)),
                ("expires_at", models.DateTimeField(help_text="Expiration timestamp for this verification request.")),
                ("attempts", models.PositiveIntegerField(default=0, help_text="Number of verification attempts made.")),
                ("max_attempts", models.PositiveIntegerField(default=5, help_text="Maximum allowed verification attempts.")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("verified", "Verified"), ("expired", "Expired"), ("failed", "Failed")], default="pending", help_text="Current status of the verification request.", max_length=16)),
                ("verified_at", models.DateTimeField(blank=True, help_text="Timestamp when verification succeeded.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="When this verification was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="When this verification was last updated.")),
            ],
            options={
                "verbose_name": "Verification Request",
                "verbose_name_plural": "Verification Requests",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["channel", "target"], name="notify_not_channel_3e606a_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["status"], name="notify_not_status_644f4f_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["created_at"], name="notify_not_created_0c1841_idx"),
        ),
        migrations.AddIndex(
            model_name="verificationrequest",
            index=models.Index(fields=["channel", "target", "method", "purpose"], name="notify_ver_channel_852b93_idx"),
        ),
        migrations.AddIndex(
            model_name="verificationrequest",
            index=models.Index(fields=["expires_at"], name="notify_ver_expires_69207a_idx"),
        ),
        migrations.AddIndex(
            model_name="verificationrequest",
            index=models.Index(fields=["status"], name="notify_ver_status_85f9c4_idx"),
        ),
        migrations.AddIndex(
            model_name="verificationrequest",
            index=models.Index(fields=["code"], name="notify_ver_code_a71fa5_idx"),
        ),
        migrations.AddIndex(
            model_name="verificationrequest",
            index=models.Index(fields=["token"], name="notify_ver_token_84684c_idx"),
        ),
    ]

