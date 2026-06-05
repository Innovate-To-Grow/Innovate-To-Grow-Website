from django.conf import settings
from rest_framework.throttling import UserRateThrottle


class PastProjectShareRateThrottle(UserRateThrottle):
    # Creating a share requires authentication, so throttle per-user (not per-anon-IP).
    scope = "past_project_share"

    def get_rate(self):
        # Read the rate live from settings. UserRateThrottle.THROTTLE_RATES is captured
        # at import time, so reading it directly would ignore override_settings in tests
        # (and any runtime change). The scope is always present in DEFAULT_THROTTLE_RATES.
        return settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][self.scope]
