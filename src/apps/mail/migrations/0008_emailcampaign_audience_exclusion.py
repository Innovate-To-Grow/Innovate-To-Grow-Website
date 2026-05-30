import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mail", "0007_alter_recipientlog_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailcampaign",
            name="exclude_audience_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "No exclusion"),
                    ("subscribers", "All Email Subscribers"),
                    ("event_registrants", "Event Registrants"),
                    ("ticket_type", "Event Ticket Type"),
                    ("checked_in", "Checked-In Attendees"),
                    ("not_checked_in", "No-Shows (Not Checked In)"),
                    ("all_members", "All Active Members"),
                    ("staff", "Staff Members"),
                    ("selected_members", "Selected Members"),
                ],
                default="",
                help_text="Optionally remove recipients who belong to this group from the primary audience.",
                max_length=32,
                verbose_name="Exclude audience",
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="exclude_event",
            field=models.ForeignKey(
                blank=True,
                help_text="Event for the exclusion audience (when excluding event-based groups).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="event.event",
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="exclude_ticket_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Ticket UUID when exclude audience is 'Event Ticket Type' (same format as primary ticket campaigns).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="emailcampaign",
            name="exclude_members",
            field=models.ManyToManyField(
                blank=True,
                help_text="Members to exclude when exclude audience is 'Selected Members'.",
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
