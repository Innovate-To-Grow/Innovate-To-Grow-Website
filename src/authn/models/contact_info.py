from django.db import models


class ContactEmail(models.Model):

    # contact email
    email_address = models.EmailField(unique=True)

    # contact email type
    EMAIL_TYPE_CHOICES = [
        ('school', 'School'),
        ('work', 'Work'),
        ('personal', 'Personal'),
        ('other', 'Other'),
    ]

    # contact email type
    ctype = models.CharField(max_length=255, choices=EMAIL_TYPE_CHOICES)

    # subscribe
    subscribe = models.BooleanField(default=False)

    # time stamp
    create_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # truncate contact email info tostring
        str_contact_email = f"{email} - {self.ctype}"

        # append subscribe info to string
        if self.subscribe:
            str_contact_email += " - Subscribed"

        return str_contact_email

    # check if email is verified (you might want to add verification later)
    @property
    def is_verified(self):
        """
        Check if the email is verified. For now, return subscribe status.
        """
        return self.subscribe


class ContactPhone(models.Model):
    # contact phone number
    phone_number = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Contact Phone Number (e.g. +1234567890)"
    )

    # contact phone region
    contact_phone_region_choices = [
        ('1', 'United States'),
        ('86', 'China P.R.C.'),
        ('886', 'Taiwan R.O.C.'),
    ]

    # contact phone region
    region = models.CharField(
        max_length=20,
        choices=contact_phone_region_choices,
        help_text="Region of the phone number"
    )

    # subscribe
    subscribe = models.BooleanField(
        default=False
    )

    # time stamp
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Contact Phone"
        verbose_name_plural = "Contact Phones"
        ordering = ['-created_at']

    def __str__(self):
        # truncate contact phone info tostring
        str_contact_phone = f"+({self.region}) {self.phone_number}"

        # append subscribe info to string
        if self.subscribe:
            str_contact_phone += " - Subscribed"

        return str_contact_phone

    # get formatted phone number
    def get_formatted_number(self):
        """
        Return a formatted phone number with country code.
        """
        return f"+{self.region}{self.phone_number}"

    # get region display name
    def get_region_display_name(self):
        """
        Return the display name for the region.
        """
        region_dict = dict(self.contact_phone_region_choices)
        return region_dict.get(self.region, self.region)




class MemberContactInfo(models.Model):

    # foreign key link to user
    model_user = models.ForeignKey('authn.Member', on_delete=models.CASCADE)

    # contact email
    contact_email = models.ForeignKey(ContactEmail, on_delete=models.CASCADE)

    # contact phone
    contact_phone = models.ForeignKey(ContactPhone, on_delete=models.CASCADE)

    # time stamp
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.model_user.username} - Member Contact Info"

    # get formatted contact info
    def get_formatted_contact_info(self):
        """
        Return formatted contact information.
        """
        email = f"Email: {self.contact_email.contact_email}"
        phone = f"Phone: {self.contact_phone.get_formatted_number()}"
        return f"{email}\n{phone}"

    # check if both email and phone are subscribed
    @property
    def is_fully_subscribed(self):
        """
        Check if both email and phone are subscribed to communications.
        """
        return self.contact_email.subscribe and self.contact_phone.subscribe
