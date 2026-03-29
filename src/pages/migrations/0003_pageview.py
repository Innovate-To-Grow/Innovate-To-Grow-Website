"""Add PageView model to pages app for page-view analytics tracking."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0002_newsfeedsource_newsarticle_newssynclog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PageView",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("path", models.CharField(db_index=True, max_length=2048)),
                ("referrer", models.URLField(blank=True, default="", max_length=2048)),
                ("user_agent", models.TextField(blank=True, default="")),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, db_index=True, null=True),
                ),
                (
                    "member",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="page_views",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "session_key",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Page View",
                "verbose_name_plural": "Page Views",
                "db_table": "analytics_pageview",
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="pageview",
            index=models.Index(
                fields=["path", "timestamp"],
                name="analytics_p_path_51c7b7_idx",
            ),
        ),
    ]
