# Publishing workflow migration: adds status field, migrates data, removes old published boolean.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_page_published_to_status(apps, schema_editor):
    """Convert Page.published boolean to Page.status string."""
    Page = apps.get_model("pages", "Page")
    # Pages with published=True get status="published"
    Page.objects.filter(published=True).update(status="published")
    # Pages with published=False get status="draft" (already the default)


def migrate_homepage_active_to_status(apps, schema_editor):
    """Set HomePage.status based on is_active."""
    HomePage = apps.get_model("pages", "HomePage")
    # Active home pages are considered published
    HomePage.objects.filter(is_active=True).update(status="published")
    # Inactive remain as "draft" (the default)


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ============================================================
        # Step 1: Add new fields to Page (keep old 'published' for now)
        # ============================================================
        migrations.AddField(
            model_name="page",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("review", "In Review"),
                    ("published", "Published"),
                ],
                db_index=True,
                default="draft",
                help_text="Publishing workflow status.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="published_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when the page was first published.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="published_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who published this content.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_published",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="submitted_for_review_at",
            field=models.DateTimeField(
                blank=True, help_text="Timestamp when submitted for review.", null=True
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="submitted_for_review_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who submitted for review.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_submitted_review",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ============================================================
        # Step 2: Add new fields to HomePage
        # ============================================================
        migrations.AddField(
            model_name="homepage",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("review", "In Review"),
                    ("published", "Published"),
                ],
                db_index=True,
                default="draft",
                help_text="Publishing workflow status.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="homepage",
            name="published_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when this home page was first published.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="homepage",
            name="published_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who published this home page.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="homepages_published",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="homepage",
            name="submitted_for_review_at",
            field=models.DateTimeField(
                blank=True, help_text="Timestamp when submitted for review.", null=True
            ),
        ),
        migrations.AddField(
            model_name="homepage",
            name="submitted_for_review_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who submitted for review.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="homepages_submitted_review",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ============================================================
        # Step 3: Data migration - copy published boolean to status
        # ============================================================
        migrations.RunPython(
            migrate_page_published_to_status,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            migrate_homepage_active_to_status,
            reverse_code=migrations.RunPython.noop,
        ),
        # ============================================================
        # Step 4: Remove old published boolean from Page
        # ============================================================
        migrations.RemoveField(
            model_name="page",
            name="published",
        ),
    ]
