import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0005_ticket_login_token_state"),
        ("mail", "0014_scamdetectorconfig"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(old_name="MagicLoginToken", new_name="LoginLinkToken"),
        migrations.AlterField(
            model_name="loginlinktoken",
            name="member",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="login_link_tokens",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="loginlinktoken",
            name="registration",
            field=models.ForeignKey(
                blank=True,
                help_text="Set when this link was issued by a ticket confirmation email.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="login_tokens",
                to="event.eventregistration",
            ),
        ),
        migrations.AddField(
            model_name="loginlinktoken",
            name="redirect_path",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text="Per-token post-login destination; used when the token has no campaign.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="login_link_validity_days",
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text=(
                    "How long each recipient's {{login_link}} stays valid after this campaign is sent (1-90 days)."
                ),
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(90),
                ],
                verbose_name="Login link validity (days)",
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="login_link_reusable",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow recipients to sign in with their {{login_link}} repeatedly until it expires. "
                    "Off: each link works exactly once. This is checked at login time, so unticking it "
                    "later immediately blocks further reuse of links from this campaign."
                ),
                verbose_name="Reusable login links",
            ),
        ),
    ]
