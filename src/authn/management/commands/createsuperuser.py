"""
Custom createsuperuser command that prompts for email and creates a ContactEmail record.

Since Member.email is no longer used (emails are stored in ContactEmail),
the default createsuperuser would create a superuser without any email.
This override prompts for email and creates the corresponding ContactEmail.
"""

from django.contrib.auth.management.commands.createsuperuser import Command as BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Run the default createsuperuser first
        super().handle(*args, **options)

        # After successful creation, prompt for email and create ContactEmail
        from django.contrib.auth import get_user_model

        from authn.models import ContactEmail

        Member = get_user_model()
        username = options.get(Member.USERNAME_FIELD)

        # In interactive mode, we need to find the just-created user
        if not username:
            # The parent command stores the username on the instance
            # We need to get it from the database - find the most recently created superuser
            member = Member.objects.filter(is_staff=True).order_by("-date_joined").first()
        else:
            member = Member.objects.filter(**{Member.USERNAME_FIELD: username}).first()

        if not member:
            return

        # Check if this member already has a primary ContactEmail
        if member.contact_emails.filter(email_type="primary").exists():
            return

        # Prompt for email
        email = None
        if not options.get("interactive", True):
            return

        while not email:
            email = input("Email address: ").strip()
            if not email:
                self.stderr.write("Error: Email address cannot be blank.")
                email = None
                continue

            # Check for uniqueness
            if ContactEmail.objects.filter(email_address__iexact=email).exists():
                self.stderr.write(f"Error: A contact email with address '{email}' already exists.")
                email = None

        ContactEmail.objects.create(
            member=member,
            email_address=email,
            email_type="primary",
            verified=True,
            subscribe=True,
        )
        self.stdout.write(f"ContactEmail '{email}' created for superuser '{member.username}'.")
