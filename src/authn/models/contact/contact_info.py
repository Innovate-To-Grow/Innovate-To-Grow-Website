from django.db import models

from authn.models.contact.phone_regions import PHONE_REGION_CHOICES
from core.models.base import TimeStampedModel


class ContactEmail(TimeStampedModel):
    # contact email
    email_address = models.EmailField(unique=True, help_text="Email address for contact", verbose_name="Email Address")

    # contact email type
    EMAIL_TYPE_CHOICES = [
        ("primary", "Primary"),
        ("secondary", "Secondary"),
        ("other", "Other"),
    ]

    # contact email type
    email_type = models.CharField(
        max_length=255,
        choices=EMAIL_TYPE_CHOICES,
        default="primary",
        help_text="Type of email address",
        verbose_name="Email Type",
    )

    # subscribe
    subscribe = models.BooleanField(
        default=False, help_text="Whether the email is subscribed to communications", verbose_name="Subscribed"
    )

    # verified
    verified = models.BooleanField(
        default=False, help_text="Whether the email address has been verified", verbose_name="Verified"
    )

    class Meta:
        verbose_name = "Contact Email"
        verbose_name_plural = "Contact Emails"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email_address"]),
            models.Index(fields=["email_type"]),
            models.Index(fields=["verified"]),
        ]

    def __str__(self):
        # truncate contact email info tostring
        str_contact_email = f"{self.email_address} - {self.get_email_type_display()}"

        # append subscribe info to string
        if self.subscribe:
            str_contact_email += " - Subscribed"

        # append verified info to string
        if self.verified:
            str_contact_email += " - Verified"

        return str_contact_email


class ContactPhone(TimeStampedModel):
    # contact phone number
    phone_number = models.CharField(max_length=20, unique=True, help_text="Contact Phone Number (e.g. +1234567890)")

    # contact phone region
    region = models.CharField(max_length=20, choices=PHONE_REGION_CHOICES, help_text="Region of the phone number")

    # subscribe
    subscribe = models.BooleanField(
        default=False, help_text="Whether the phone number is subscribed to communications", verbose_name="Subscribed"
    )

    class Meta:
        verbose_name = "Contact Phone"
        verbose_name_plural = "Contact Phones"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["region"]),
            models.Index(fields=["subscribe"]),
        ]

    def __str__(self):
        # truncate contact phone info tostring
        region_display = self.get_region_display_name()
        str_contact_phone = f"+{self.region.split('-')[0] if '-' in self.region else self.region} {self.phone_number} ({region_display})"

        # append subscribe info to string
        if self.subscribe:
            str_contact_phone += " - Subscribed"

        return str_contact_phone

    # get formatted phone number
    def get_formatted_number(self):
        """
        Return a formatted phone number with country code.
        Extracts the numeric country code from region (handles '1-US', '1-CA' format).
        """
        # Extract numeric country code (handle '1-US', '1-CA' format)
        country_code = self.region.split("-")[0] if "-" in self.region else self.region
        return f"+{country_code}{self.phone_number}"

    # get region display name
    def get_region_display_name(self):
        """
        Return the display name for the region.
        """
        region_dict = dict(PHONE_REGION_CHOICES)
        return region_dict.get(self.region, self.region)


class MemberContactInfo(TimeStampedModel):
    # foreign key link to user
    model_user = models.ForeignKey(
        "authn.Member",
        on_delete=models.CASCADE,
        related_name="contact_infos",
        help_text="Member this contact information belongs to",
        verbose_name="Member",
    )

    # contact email
    contact_email = models.ForeignKey(
        ContactEmail,
        on_delete=models.CASCADE,
        related_name="member_contact_infos",
        help_text="Contact email address",
        verbose_name="Contact Email",
    )

    # contact phone
    contact_phone = models.ForeignKey(
        ContactPhone,
        on_delete=models.CASCADE,
        related_name="member_contact_infos",
        help_text="Contact phone number",
        verbose_name="Contact Phone",
    )

    class Meta:
        verbose_name = "Member Contact Info"
        verbose_name_plural = "Member Contact Infos"
        ordering = ["-created_at"]
        # Ensure one member can have multiple contact info entries
        # but prevent exact duplicates
        unique_together = [["model_user", "contact_email", "contact_phone"]]
        indexes = [
            models.Index(fields=["model_user"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.model_user.username} - Member Contact Info"

    # get formatted contact info
    def get_formatted_contact_info(self):
        """
        Return formatted contact information.
        """
        email = f"Email: {self.contact_email.email_address}"
        phone = f"Phone: {self.contact_phone.get_formatted_number()}"
        return f"{email}\n{phone}"

    # check if both email and phone are subscribed
    @property
    def is_fully_subscribed(self):
        """
        Check if both email and phone are subscribed to communications.
        """
        return self.contact_email.subscribe and self.contact_phone.subscribe

    # check if email is verified
    @property
    def is_email_verified(self):
        """
        Check if the email address is verified.
        """
        return self.contact_email.verified
