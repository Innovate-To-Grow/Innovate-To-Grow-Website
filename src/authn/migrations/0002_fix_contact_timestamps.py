from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("authn", "0001_initial"),
    ]

    operations = [
        # ContactEmail: align field names and timestamps with current model
        migrations.RenameField(
            model_name="contactemail",
            old_name="ctype",
            new_name="email_type",
        ),
        migrations.RenameField(
            model_name="contactemail",
            old_name="create_at",
            new_name="created_at",
        ),
        migrations.AddField(
            model_name="contactemail",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                help_text="When this email was last updated",
                verbose_name="Updated At",
            ),
        ),
        migrations.AddField(
            model_name="contactemail",
            name="verified",
            field=models.BooleanField(
                default=False,
                help_text="Whether the email address has been verified",
                verbose_name="Verified",
            ),
        ),
        # ContactPhone: add updated_at to match model
        migrations.AddField(
            model_name="contactphone",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                help_text="When this phone number was last updated",
                verbose_name="Updated At",
            ),
        ),
        # MemberContactInfo: add created_at to match model
        migrations.AddField(
            model_name="membercontactinfo",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                help_text="When this contact information was created",
                verbose_name="Created At",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="membercontactinfo",
            unique_together={("model_user", "contact_email", "contact_phone")},
        ),
    ]

