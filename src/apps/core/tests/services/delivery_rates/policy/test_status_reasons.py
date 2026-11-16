"""Every reason a provider adapter can pause or stop a channel for has words on Mail → Delivery Rates."""

import ast
from pathlib import Path

from django.test import SimpleTestCase

from apps.core.services import delivery_rates, email
from apps.core.services.delivery_rates.rules.signals import Reason
from apps.core.services.delivery_rates.status_text import REASONS, reason

_CONSTRUCTORS = {"throttle", "pause", "quota", "blocked"}


def _emitted_codes() -> set[str]:
    """The literal reason codes passed to the signal constructors by the adapters and the email providers."""
    roots = (Path(delivery_rates.__file__).parent / "adapters", Path(email.__file__).parent)
    codes = set()
    for root in roots:
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                first = node.args[0]
                if name in _CONSTRUCTORS and isinstance(first, ast.Constant) and isinstance(first.value, str):
                    codes.add(first.value)
    return codes


class StatusReasonTests(SimpleTestCase):
    def test_every_adapter_reason_and_limiter_reason_has_text(self):
        codes = _emitted_codes() | {str(member) for member in Reason}

        self.assertGreater(len(codes), 15)  # the scan found the adapters
        self.assertEqual(sorted(code for code in codes if code not in REASONS), [])

    def test_reasons_read_as_a_sentence_after_the_provider(self):
        self.assertEqual(
            reason("The Gmail API", "daily_sending_limit"),
            "The Gmail API reports the account's daily sending limit is reached",
        )
        self.assertEqual(reason("AWS SMS", "made_up"), "AWS SMS stopped (made_up)")
