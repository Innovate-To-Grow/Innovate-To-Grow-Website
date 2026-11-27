"""Tickets have no owner (I2G-HELPDESK-01): the assignee, the assignment group, a category's default group and the
assignment-notice switch are deprecated. This changes Django's model state only (they are no longer editable, and
their help texts say so); it runs no SQL. The columns, the AssignmentGroup table and its members table keep their
data, stay nullable (or keep their database default), and a release still running during the deploy keeps reading
and writing them. Django still knows the fields, so deleting a member still clears them (SET_NULL, the members row).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("helpdesk", "0006_guard_legacy_list_senders"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="assignmentgroup",
                    name="members",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Deprecated: tickets have no owner.",
                        related_name="helpdesk_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="helpdesksettings",
                    name="notify_assignment",
                    field=models.BooleanField(
                        db_default=True,
                        default=True,
                        editable=False,
                        help_text="Deprecated: staff get no helpdesk email.",
                    ),
                ),
                migrations.AlterField(
                    model_name="helpdesksettings",
                    name="shadow_mode",
                    field=models.BooleanField(
                        default=True,
                        help_text="On: nothing is ever sent (no replies or acknowledgements); staff answer from Outlook. Off: staff can reply to the requester from the ticket page, and the acknowledgement below is sent when it is switched on. The mailbox is only ever read either way.",
                    ),
                ),
                migrations.AlterField(
                    model_name="ticket",
                    name="assignee",
                    field=models.ForeignKey(
                        blank=True,
                        editable=False,
                        help_text="Deprecated: tickets have no owner.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="helpdesk_assigned_tickets",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned to",
                    ),
                ),
                migrations.AlterField(
                    model_name="ticket",
                    name="assignment_group",
                    field=models.ForeignKey(
                        blank=True,
                        editable=False,
                        help_text="Deprecated: tickets have no owner.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tickets",
                        to="helpdesk.assignmentgroup",
                    ),
                ),
                migrations.AlterField(
                    model_name="ticketcategory",
                    name="default_group",
                    field=models.ForeignKey(
                        blank=True,
                        editable=False,
                        help_text="Deprecated: tickets have no owner.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="default_for_categories",
                        to="helpdesk.assignmentgroup",
                    ),
                ),
            ],
        ),
    ]
