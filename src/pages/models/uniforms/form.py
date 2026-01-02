import uuid
from django.db import models
from django.db.models import F

from core.models.base import AuthoredModel, SoftDeleteModel, TimeStampedModel


def default_form_fields():
    """
    Default empty form fields structure.

    Returns an empty list that will be populated with field definitions
    in the Django admin interface.
    """
    return []


class UniformForm(TimeStampedModel, SoftDeleteModel, AuthoredModel):
    """
    Dynamic form builder model that stores form definitions as JSON.

    Admins can create custom forms with various field types (text, email,
    select, etc.) and the form structure is stored flexibly in the fields
    JSONField without requiring schema changes.
    """

    # Identification
    form_uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="Unique identifier for this form"
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable form name (e.g., 'Event Registration')"
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier for this form"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the form's purpose"
    )

    # Form Configuration
    fields = models.JSONField(
        default=default_form_fields,
        help_text="JSON array of form field definitions with types, labels, validation rules, etc."
    )

    # Form Settings
    submit_button_text = models.CharField(
        max_length=100,
        default="Submit",
        help_text="Text displayed on the submit button"
    )
    success_message = models.TextField(
        default="Thank you for your submission!",
        help_text="Message displayed after successful submission"
    )
    redirect_url = models.URLField(
        blank=True,
        null=True,
        help_text="Optional URL to redirect to after submission"
    )

    # Email Notifications
    enable_email_notification = models.BooleanField(
        default=True,
        help_text="Send email notification when form is submitted"
    )
    notification_recipients = models.TextField(
        blank=True,
        help_text="Comma-separated email addresses to notify on submission"
    )
    email_subject_template = models.CharField(
        max_length=255,
        blank=True,
        help_text="Template for email subject (leave blank for default)"
    )

    # Publishing & Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this form accepts new submissions"
    )
    published = models.BooleanField(
        default=False,
        help_text="Whether this form is publicly visible"
    )

    # Submission Settings
    allow_anonymous = models.BooleanField(
        default=True,
        help_text="Allow submissions from users who are not logged in"
    )
    login_required = models.BooleanField(
        default=False,
        help_text="Require users to be logged in to submit this form"
    )
    max_submissions_per_user = models.PositiveIntegerField(
        default=0,
        help_text="Maximum submissions per user (0 = unlimited)"
    )

    # Analytics
    submission_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of submissions received"
    )

    class Meta:
        db_table = "pages_uniformform"
        ordering = ['-created_at']
        verbose_name = "Form"
        verbose_name_plural = "Forms"
        indexes = [
            models.Index(fields=['slug'], name='pages_form_slug_idx'),
            models.Index(fields=['is_active', 'published'], name='pages_form_active_pub_idx'),
            models.Index(fields=['created_at'], name='pages_form_created_idx'),
        ]

    def __str__(self):
        status = " (Active)" if self.is_active and self.published else ""
        return f"{self.name}{status}"

    def get_absolute_url(self):
        """Return the public URL for this form."""
        return f'/forms/{self.slug}/'

    def increment_submission_count(self):
        """Increment the submission count atomically."""
        self.submission_count = F('submission_count') + 1
        self.save(update_fields=['submission_count'])

    def get_fields_by_order(self):
        """Return fields sorted by their order property."""
        return sorted(self.fields, key=lambda x: x.get('order', 0))

    def validate_submission_data(self, data):
        """
        Validate submission data against field definitions.

        Returns a dictionary of field names to error messages.
        Empty dict means validation passed.
        """
        errors = {}

        for field_def in self.fields:
            field_name = field_def.get('name')
            field_label = field_def.get('label', field_name)
            field_type = field_def.get('field_type')
            required = field_def.get('required', False)
            validation = field_def.get('validation', {})

            # Check required fields
            if required and (field_name not in data or not data[field_name]):
                error_msg = validation.get('error_messages', {}).get(
                    'required',
                    f"{field_label} is required"
                )
                errors[field_name] = error_msg
                continue

            # Skip further validation if field is empty and not required
            if field_name not in data or not data[field_name]:
                continue

            value = data[field_name]

            # Length validation for text fields
            if field_type in ['text', 'textarea', 'email', 'tel', 'url']:
                if 'min_length' in validation and len(str(value)) < validation['min_length']:
                    errors[field_name] = f"{field_label} must be at least {validation['min_length']} characters"
                if 'max_length' in validation and len(str(value)) > validation['max_length']:
                    errors[field_name] = f"{field_label} cannot exceed {validation['max_length']} characters"

            # Number validation
            if field_type == 'number':
                try:
                    num_value = float(value)
                    if 'min' in validation and num_value < validation['min']:
                        errors[field_name] = f"{field_label} must be at least {validation['min']}"
                    if 'max' in validation and num_value > validation['max']:
                        errors[field_name] = f"{field_label} cannot exceed {validation['max']}"
                except (ValueError, TypeError):
                    errors[field_name] = f"{field_label} must be a valid number"

        return errors

    @classmethod
    def get_active_forms(cls):
        """Return all active and published forms."""
        return cls.objects.filter(is_active=True, published=True)

