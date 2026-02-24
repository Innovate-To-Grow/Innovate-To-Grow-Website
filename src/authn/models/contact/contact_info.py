from django.db import models

from authn.models.contact.phone_regions import PHONE_REGION_CHOICES
from core.models import ProjectControlModel


class ContactEmail(ProjectControlModel):
    # owner
    member = models.ForeignKey(
        "authn.Member",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contact_emails",
        help_text="Member this email belongs to",
        verbose_name="Member",
    )

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


class ContactPhone(ProjectControlModel):
    # owner
    member = models.ForeignKey(
        "authn.Member",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contact_phones",
        help_text="Member this phone belongs to",
        verbose_name="Member",
    )

    # contact phone number
    phone_number = models.CharField(max_length=20, unique=True, help_text="Contact Phone Number (e.g. +1234567890)")

    # contact phone region
    region = models.CharField(max_length=20, choices=PHONE_REGION_CHOICES, help_text="Region of the phone number")

    # subscribe
    subscribe = models.BooleanField(
        default=False, help_text="Whether the phone number is subscribed to communications", verbose_name="Subscribed"
    )
    verified = models.BooleanField(
        default=False,
        help_text="Whether the phone number has been verified",
        verbose_name="Verified",
    )

    class Meta:
        verbose_name = "Contact Phone"
        verbose_name_plural = "Contact Phones"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["region"]),
            models.Index(fields=["subscribe"]),
            models.Index(fields=["verified"]),
        ]

    def __str__(self):
        # truncate contact phone info tostring
        region_display = self.get_region_display_name()
        str_contact_phone = f"+{self.region.split('-')[0] if '-' in self.region else self.region} {self.phone_number} ({region_display})"

        # append subscribe info to string
        if self.subscribe:
            str_contact_phone += " - Subscribed"
        if self.verified:
            str_contact_phone += " - Verified"

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


