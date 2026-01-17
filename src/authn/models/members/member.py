import uuid

from django.contrib.auth.models import (
    AbstractUser,
    Group,
)
from django.db import models

from core.models import ProjectControlModel

from ..contact.contact_info import MemberContactInfo
from .user_group import MemberGroup


class Member(AbstractUser, ProjectControlModel):
    # member uuid
    member_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="Member UUID")

    # add field for user models
    middle_name = models.CharField(max_length=255, null=True, blank=True, help_text="Middle Name")

    # member account
    contect_email = models.ForeignKey("authn.ContactEmail", on_delete=models.CASCADE, null=True, blank=True)

    # organization
    organization = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Organization or company the member belongs to",
        verbose_name="Organization",
    )

    # user status
    is_active_member = models.BooleanField(default=True, help_text="Designates whether this user is an active member.")

    # assign to a group
    def assign_group(self, group_name: str):
        # handle group not found
        if group_name not in MemberGroup.GROUP_CHOICES:
            raise ValueError(f"Group '{group_name}' not found")

        # get or create the group
        group, created = Group.objects.get_or_create(name=group_name)

        # add user to the group
        self.groups.add(group)

    # remove user from a group
    def remove_from_group(self, group_name: str):
        # get group
        group = Group.objects.filter(name=group_name).first()

        if group:
            # remove user from the group
            self.groups.remove(group)
        else:
            raise ValueError(f"Group '{group_name}' not found")

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

    # check if user is in a specific group
    def is_in_group(self, group_name: str) -> bool:
        """
        Check if the user is in a specific group.
        """
        return self.groups.filter(name=group_name).exists()

    # get all user groups as list
    def get_group_names(self) -> list:
        """
        Return a list of all group names the user belongs to.
        """
        return list(self.groups.values_list("name", flat=True))

    # check if user has a specific role
    def has_role(self, role_name: str) -> bool:
        """
        Check if the user has a specific role (same as is_in_group for now).
        """
        return self.is_in_group(role_name)

    # get user profile
    def get_profile(self):
        """
        Get or create the user's profile.
        """
        profile, created = MemberProfile.objects.get_or_create(model_user=self)
        return profile

    # get primary contact info
    def get_primary_contact_info(self):
        """
        Get the user's primary contact information.
        """
        contact_info = MemberContactInfo.objects.filter(model_user=self).first()
        return contact_info


class MemberProfile(ProjectControlModel):
    # foreign key link to user
    model_user = models.OneToOneField(Member, on_delete=models.CASCADE)

    # user display name
    display_name = models.TextField(null=True, blank=True, help_text=("User Display Name"), verbose_name="Display Name")

    # user profile image (base64 encoded png 128*128)
    profile_image = models.TextField(
        null=True,
        blank=True,
        help_text=("User Profile Image, Base64 Encoded PNG 128*128"),
        verbose_name="Profile Image (Base64 Encoded PNG)",
    )

    def __str__(self):
        return f"{self.model_user.username} - User Profile"

    # get display name with fallback
    def get_display_name(self):
        """
        Return display name if available, otherwise return user's full name.
        """
        if self.display_name:
            return self.display_name
        return self.model_user.get_full_name() or self.model_user.username

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
