from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

from scripts.ci.validate_dependabot_labels import existing_repo_labels


def api_response(labels: list[dict[str, str]]) -> io.BytesIO:
    return io.BytesIO(json.dumps(labels).encode("utf-8"))


class ValidateDependabotLabelsTests(unittest.TestCase):
    def test_transient_api_failures_recover(self) -> None:
        failures = (
            urllib.error.HTTPError("https://api.github.com", 503, "unavailable", None, None),
            urllib.error.HTTPError("https://api.github.com", 429, "rate limited", None, None),
            urllib.error.URLError("connection refused"),
            TimeoutError("timed out"),
            ConnectionError("connection reset"),
        )
        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                mock.patch("scripts.ci.validate_dependabot_labels.urllib.request.urlopen") as urlopen,
                mock.patch("scripts.ci.validate_dependabot_labels.time.sleep") as sleep,
            ):
                urlopen.side_effect = [failure, api_response([{"name": "dependencies"}]), api_response([])]

                self.assertEqual(existing_repo_labels("owner/repo", "token"), {"dependencies"})
                self.assertEqual(urlopen.call_count, 3)
                sleep.assert_called_once_with(1)

    def test_non_retryable_http_error_fails_immediately(self) -> None:
        for status in (400, 401, 403, 404):
            with (
                self.subTest(status=status),
                mock.patch("scripts.ci.validate_dependabot_labels.urllib.request.urlopen") as urlopen,
                mock.patch("scripts.ci.validate_dependabot_labels.time.sleep") as sleep,
            ):
                urlopen.side_effect = urllib.error.HTTPError("https://api.github.com", status, "error", None, None)

                with self.assertRaises(urllib.error.HTTPError):
                    existing_repo_labels("owner/repo", "token")
                urlopen.assert_called_once()
                sleep.assert_not_called()

    def test_transient_error_stops_after_three_attempts(self) -> None:
        with (
            mock.patch("scripts.ci.validate_dependabot_labels.urllib.request.urlopen") as urlopen,
            mock.patch("scripts.ci.validate_dependabot_labels.time.sleep") as sleep,
        ):
            urlopen.side_effect = urllib.error.HTTPError("https://api.github.com", 502, "bad gateway", None, None)

            with self.assertRaises(urllib.error.HTTPError):
                existing_repo_labels("owner/repo", "token")
            self.assertEqual(urlopen.call_count, 3)
            self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2)])

    def test_retry_on_second_page_preserves_first_page_labels(self) -> None:
        with (
            mock.patch("scripts.ci.validate_dependabot_labels.urllib.request.urlopen") as urlopen,
            mock.patch("scripts.ci.validate_dependabot_labels.time.sleep") as sleep,
        ):
            urlopen.side_effect = [
                api_response([{"name": "backend"}]),
                TimeoutError("timed out"),
                api_response([{"name": "frontend"}]),
                api_response([]),
            ]

            self.assertEqual(existing_repo_labels("owner/repo", "token"), {"backend", "frontend"})
            urls = [call.args[0].full_url for call in urlopen.call_args_list]
            self.assertEqual([url.rsplit("=", 1)[-1] for url in urls], ["1", "2", "2", "3"])
            sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
