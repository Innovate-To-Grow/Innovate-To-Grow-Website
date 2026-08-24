from __future__ import annotations

import unittest

from scripts.ci.check_npm_licenses import ALLOWED_LICENSES


class NpmLicenseAllowlistTests(unittest.TestCase):
    def test_sil_open_font_license_is_explicitly_allowed(self) -> None:
        self.assertIn("OFL-1.1", ALLOWED_LICENSES)


if __name__ == "__main__":
    unittest.main()
