from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.email import (
    GraphProvider,
    UncertainEmailDeliveryError,
)
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    KEY_LINE,
    PROVIDER_LOGGER,
    GraphFixtureMixin,
    make_provider,
    simple_message,
)


class GraphUnexpectedErrorTests(GraphFixtureMixin, SimpleTestCase):
    def test_an_unexpected_error_after_the_callback_is_uncertain_and_leaks_nothing(self):
        leaky = ValueError(f"Invalid header value 'Bearer {ACCESS_TOKEN}' for {KEY_LINE}")
        provider = make_provider()

        with (
            patch.object(GraphProvider, "_post", side_effect=leaky),
            self.assertLogs(PROVIDER_LOGGER, level="ERROR") as logs,
            self.assertRaises(UncertainEmailDeliveryError) as caught,
        ):
            provider.send(simple_message())

        error = caught.exception
        self.assertEqual(error.outcome, PROVIDER_OUTCOME_UNCERTAIN)
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)
        logged = "\n".join(logs.output)
        self.assertIn("ValueError", logged)
        for leaked in (ACCESS_TOKEN, KEY_LINE):
            self.assertNotIn(leaked, str(error))
            self.assertNotIn(leaked, logged)

    def test_the_callback_still_runs_before_the_safety_net_and_its_errors_still_propagate(self):
        callback_error = RuntimeError("claim lost")
        provider = make_provider()

        with self.assertRaises(RuntimeError) as caught:
            provider.send(simple_message(), before_provider_call=MagicMock(side_effect=callback_error))

        self.assertIs(caught.exception, callback_error)
        self.assertEqual(self.fake.send_requests, [])
