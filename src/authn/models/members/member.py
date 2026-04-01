from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import ProjectControlModel

from .manager import MemberManager


class Member(AbstractUser, ProjectControlModel):
    username = None

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = MemberManager()

    def get_username(self):
        """Return UUID as a string so templates and admin can handle it."""
        return str(self.id)

    def __str__(self):
        return self.get_full_name() or self.get_primary_email() or str(self.id)

    # add field for user models
    middle_name = models.CharField(max_length=255, null=True, blank=True, help_text="Middle Name")

    @property
    def member_uuid(self):
        """Return the member's UUID (alias for id from ProjectControlModel)."""
        return self.id

    # organization
    organization = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Organization or company the member belongs to",
        verbose_name="Organization",
    )

    # email subscription
    email_subscribe = models.BooleanField(
        default=True,
        help_text="Whether the member is subscribed to email communications.",
        verbose_name="Email Subscribe",
    )

    # get full name including middle name
    def get_full_name(self):
        """
        Return the first_name plus the middle_name plus the last_name, with a space in between.
        """
        full_name = self.first_name
        if self.middle_name:
            full_name += f" {self.middle_name}"
        if self.last_name:
            full_name += f" {self.last_name}"
        return full_name.strip()

    def get_primary_email(self) -> str:
        """Return the primary ContactEmail address, or empty string."""
        contact = self.contact_emails.filter(email_type="primary").order_by("created_at").first()
        return contact.email_address if contact else ""

    def get_primary_contact_email(self):
        """Return the primary ContactEmail object, or None."""
        return self.contact_emails.filter(email_type="primary").order_by("created_at").first()

    # get user profile
    def get_profile(self):
        """
        Return the user's profile without creating one on read.

        Returns the existing MemberProfile or an unsaved instance with defaults.
        """
        try:
            return self.memberprofile
        except MemberProfile.DoesNotExist:
            return MemberProfile(model_user=self)


class MemberProfile(ProjectControlModel):
    # foreign key link to user
    model_user = models.OneToOneField(Member, on_delete=models.CASCADE)

    # user profile image (base64 encoded png 128*128)
    profile_image = models.TextField(
        null=True,
        blank=True,
        help_text="User Profile Image, Base64 Encoded PNG 128*128",
        verbose_name="Profile Image (Base64 Encoded PNG)",
    )

    def __str__(self):
        return f"{self.model_user.get_full_name() or str(self.model_user.id)} - User Profile"

    # check if profile image exists
    def has_profile_image(self):
        """
        Check if the user has a profile image.
        """
        return bool(self.profile_image)

    # get profile image url (if you have media files setup)
    def get_profile_image_url(self):
        """
        Return profile image URL. This assumes you have proper media file handling.
        For now, returns the base64 string or None.
        """
        return self.profile_image if self.profile_image else None
