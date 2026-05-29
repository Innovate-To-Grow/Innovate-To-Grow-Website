from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailcampaign",
            name="login_redirect_path",
            field=models.CharField(
                default="/account",
                help_text="Internal site page where recipients land after one-click login.",
                max_length=200,
                verbose_name="Post-login destination",
            ),
            preserve_default=False,
        ),
    ]
