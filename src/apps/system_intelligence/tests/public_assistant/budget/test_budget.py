"""Client IPs and the budget counters' reserve / settle semantics."""

from django.test import RequestFactory, TestCase, override_settings

from apps.system_intelligence.services.public_assistant import budget


class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_remote_addr_fallback(self):
        request = self.factory.get("/", REMOTE_ADDR="203.0.113.7")
        self.assertEqual(budget.client_ip(request), "203.0.113.7")

    def test_forwarded_leftmost_without_num_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(budget.client_ip(request), "1.1.1.1")

    @override_settings(NUM_PROXIES=2)
    def test_forwarded_with_num_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3", REMOTE_ADDR="10.0.0.1")
        # 3 entries, 2 trusted hops -> Nth-from-right is index 1.
        self.assertEqual(budget.client_ip(request), "2.2.2.2")

    @override_settings(NUM_PROXIES=5)
    def test_forwarded_with_num_proxies_clamped(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2")
        self.assertEqual(budget.client_ip(request), "1.1.1.1")

    def test_empty_forwarded_falls_back(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="  ,  ", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(budget.client_ip(request), "9.9.9.9")
