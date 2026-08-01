from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RENDERER_PATH = REPOSITORY_ROOT / ".github/scripts/render_amplify_headers.py"
SPEC = importlib.util.spec_from_file_location("render_amplify_headers", RENDERER_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderAmplifyHeadersTests(unittest.TestCase):
    def test_policy_contains_cms_frames_and_backend_report_endpoint(self) -> None:
        policy = renderer.build_csp(
            "https://api.example.com/v1",
            "https://backend.example.com/api",
            "https://*.youtube.com, https://archive.example.com/",
        )
        directives = {item.strip().split(maxsplit=1)[0]: item.strip() for item in policy.split(";") if item.strip()}
        self.assertIn("https://*.youtube.com", directives["frame-src"].split())
        self.assertIn("https://archive.example.com", directives["frame-src"].split())
        self.assertEqual(directives["report-uri"], "report-uri https://backend.example.com/csp-report/")
        self.assertNotIn("'unsafe-inline'", directives["script-src"])
        self.assertNotIn("'unsafe-eval'", directives["script-src"])

    def test_frame_sources_reject_paths_and_policy_injection(self) -> None:
        for value in (
            "",
            "http://youtube.com",
            "https://youtube.com/embed/video",
            "https://youtube.com; script-src *",
        ):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit):
                    renderer.parse_frame_sources(value)

    def test_report_only_and_enforced_header_names(self) -> None:
        csp = renderer.build_csp(
            "https://api.example.com",
            "https://backend.example.com",
            "https://www.youtube.com",
        )
        report_only = renderer.build_custom_headers(csp, "report-only")
        enforced = renderer.build_custom_headers(csp, "enforce")
        self.assertIn("Content-Security-Policy-Report-Only", report_only)
        self.assertNotIn("key: 'Content-Security-Policy'", report_only)
        self.assertIn("key: 'Content-Security-Policy'", enforced)

    def test_cli_writes_a_complete_header_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "custom-headers.yml"
            csp = renderer.build_csp(
                "https://api.example.com",
                "https://backend.example.com",
                "https://www.youtube.com",
            )
            output.write_text(renderer.build_custom_headers(csp, "report-only"), encoding="utf-8")
            rendered = output.read_text(encoding="utf-8")
        self.assertTrue(rendered.startswith("customHeaders:\n"))
        self.assertIn("report-uri https://backend.example.com/csp-report/;", rendered)


if __name__ == "__main__":
    unittest.main()
