"""Test helper: run the real SMS verification service with only the provider replaced.

Patching ``start_phone_verification`` itself would skip what these tests are about (the durable challenge, the
per-number caps and the SMS daily budget, which is reserved where the SMS is dispatched). This replaces the three
things below it instead: the AWS configuration lookup, the random code and the provider call.
"""

from unittest.mock import MagicMock, patch

from apps.authn.models import SendQuotaWindow

SMS_CODE = "123456"
WRONG_CODE = "000000"


def patch_sms_provider(test_case, *, code: str = SMS_CODE) -> MagicMock:
    """Patch the provider for the rest of ``test_case``; returns the mock standing in for the provider call."""
    aws_config = MagicMock()
    aws_config.render_sms_otp_message.side_effect = lambda value: f"Your code is {value}"
    mocks = {}
    for name, kwargs in (
        ("_assert_configured", {"return_value": aws_config}),
        ("_random_code", {"return_value": code}),
        ("_publish_sms", {"return_value": "provider-message-id"}),
    ):
        patcher = patch(f"apps.authn.services.sms.sns_verify.{name}", **kwargs)
        mocks[name] = patcher.start()
        test_case.addCleanup(patcher.stop)
    return mocks["_publish_sms"]


def sms_budget_used() -> int:
    """Units of the SMS daily budget reserved so far (every day's window, so a test never depends on the date)."""
    rows = SendQuotaWindow.objects.filter(kind=SendQuotaWindow.Kind.SMS_DAILY)
    return sum(rows.values_list("reserved_count", flat=True))
