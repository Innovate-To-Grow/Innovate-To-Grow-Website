from django.test import SimpleTestCase

from apps.core.services.email.inbound import auth_summary
from apps.core.services.email.inbound.classify import spam_confidence_level


class AuthenticationSummaryTests(SimpleTestCase):
    def test_reads_the_first_result_of_each_method_and_the_scl(self):
        headers = {
            "authentication-results": ["spf=pass smtp.mailfrom=x; dkim=fail header.d=x; dmarc=fail; compauth=fail"],
            "x-ms-exchange-organization-scl": ["1"],
        }

        self.assertEqual(
            auth_summary(headers), {"spf": "pass", "dkim": "fail", "dmarc": "fail", "compauth": "fail", "scl": 1}
        )
        self.assertEqual(auth_summary({}), {})

    def test_the_highest_scl_is_used_and_garbage_is_ignored(self):
        headers = {
            "x-ms-exchange-organization-scl": ["abc"],
            "x-forefront-antispam-report": ["SCL:2;", "CIP:1;SCL:7"],
        }

        self.assertEqual(spam_confidence_level(headers), 7)
        self.assertIsNone(spam_confidence_level({"x-ms-exchange-organization-scl": ["n/a"]}))
