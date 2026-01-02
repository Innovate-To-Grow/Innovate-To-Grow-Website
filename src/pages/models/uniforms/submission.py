import uuid
from django.db import models
from django.utils import timezone

from core.models.base import TimeStampedModel


class FormSubmission(TimeStampedModel):
    """
    Stores individual form submissions with complete metadata.

    Tracks who submitted the form, what data was submitted, and the
    current processing status of the submission.
    """

    # Status choices
    STATUS_PENDING = 'pending'
    STATUS_REVIEWED = 'reviewed'
    STATUS_PROCESSED = 'processed'
    STATUS_ARCHIVED = 'archived'
    STATUS_SPAM = 'spam'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_REVIEWED, 'Reviewed'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_ARCHIVED, 'Archived'),
        (STATUS_SPAM, 'Marked as Spam'),
    ]

    # Identification
    submission_uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="Unique identifier for this submission"
    )

    # Relationships
    form = models.ForeignKey(
        'pages.UniformForm',
        on_delete=models.CASCADE,
        related_name='submissions',
        help_text="The form that was submitted"
    )
    user = models.ForeignKey(
        'authn.Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='form_submissions',
        help_text="User who submitted the form (null for anonymous submissions)"
    )

    # Submission Data
    data = models.JSONField(
        help_text="Complete form submission data as key-value pairs"
    )

    # Status Tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current processing status of this submission"
    )

    # Admin Review
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes about this submission"
    )
    reviewed_by = models.ForeignKey(
        'authn.Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_submissions',
        help_text="Admin who reviewed this submission"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this submission was reviewed"
    )

    # Security & Metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the submitter"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser user agent string"
    )
    referrer = models.URLField(
        blank=True,
        null=True,
        max_length=500,
        help_text="Page the user came from"
    )

    # Email Notification Status
    notification_sent = models.BooleanField(
        default=False,
        help_text="Whether email notification has been sent"
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was sent"
    )
    notification_error = models.TextField(
        blank=True,
        help_text="Error message if notification failed"
    )

    class Meta:
        db_table = "pages_formsubmission"
        ordering = ['-created_at']
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"
        indexes = [
            models.Index(fields=['form', 'created_at'], name='pages_formsub_form_time_idx'),
            models.Index(fields=['status'], name='pages_formsub_status_idx'),
            models.Index(fields=['user', 'created_at'], name='pages_formsub_user_time_idx'),
            models.Index(fields=['ip_address'], name='pages_formsub_ip_idx'),
        ]

    def __str__(self):
        user_info = self.user.username if self.user else "Anonymous"
        return f"{self.form.name} - {user_info} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def is_anonymous(self):
        """Check if this is an anonymous submission."""
        return self.user is None

    def mark_as_reviewed(self, admin_user):
        """Mark this submission as reviewed by the given admin."""
        self.status = self.STATUS_REVIEWED
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

