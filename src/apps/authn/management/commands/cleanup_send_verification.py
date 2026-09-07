from django.core.management.base import BaseCommand

from apps.authn.services.send_verification import cleanup_expired_records


class Command(BaseCommand):
    help = "Expire pending send-verification challenges and delete records past the retention window."

    def handle(self, *args, **options):
        result = cleanup_expired_records()
        self.stdout.write(
            self.style.SUCCESS(
                "Expired {expired_challenges} challenges; deleted {deleted_challenges} challenges "
                "and {deleted_requests} send requests.".format(**result)
            )
        )
