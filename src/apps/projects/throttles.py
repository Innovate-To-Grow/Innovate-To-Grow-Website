from django.conf import settings
from rest_framework.throttling import AnonRateThrottle


class PastProjectShareRateThrottle(AnonRateThrottle):
    scope = "past_project_share"

    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        return rates.get(self.scope, "10/minute")
