"""Move profile_image from MemberProfile to Member and delete MemberProfile."""

from django.db import migrations, models


def copy_profile_images(apps, schema_editor):
    """Copy profile_image from MemberProfile rows to their linked Member."""
    MemberProfile = apps.get_model("authn", "MemberProfile")
    for profile in MemberProfile.objects.select_related("model_user").exclude(profile_image__isnull=True).exclude(
        profile_image=""
    ):
        Member = profile.model_user
        Member.profile_image = profile.profile_image
        Member.save(update_fields=["profile_image"])


class Migration(migrations.Migration):
    dependencies = [
        ("authn", "0004_remove_admininvitation_version_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="profile_image",
            field=models.TextField(
                blank=True,
                help_text="Profile image, base64-encoded.",
                null=True,
                verbose_name="Profile Image",
            ),
        ),
        migrations.RunPython(copy_profile_images, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="MemberProfile",
        ),
    ]
