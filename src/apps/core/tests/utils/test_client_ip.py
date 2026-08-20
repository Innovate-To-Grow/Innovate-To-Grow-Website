"""Tests for apps.core.utils.client_ip NUM_PROXIES handling."""

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.utils.client_ip import client_ip


class ClientIpTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, xff=None, remote_addr="10.0.0.9"):
        meta = {"REMOTE_ADDR": remote_addr}
        if xff is not None:
            meta["HTTP_X_FORWARDED_FOR"] = xff
        return self.factory.get("/", **meta)

    def test_no_xff_returns_remote_addr(self):
        self.assertEqual(client_ip(self._request()), "10.0.0.9")

    @override_settings(NUM_PROXIES=1)
    def test_num_proxies_1_returns_the_rightmost_xff_entry(self):
        # The one trusted proxy (REMOTE_ADDR) appended the rightmost entry; everything left of it
        # is client-supplied and untrusted.
        request = self._request(xff="198.51.100.7, 192.0.2.1, 203.0.113.2")
        self.assertEqual(client_ip(request), "203.0.113.2")

    @override_settings(NUM_PROXIES=None)
    def test_num_proxies_unset_uses_leftmost_xff_entry(self):
        request = self._request(xff="203.0.113.7, 10.0.0.2")
        self.assertEqual(client_ip(request), "203.0.113.7")

    @override_settings(NUM_PROXIES=0)
    def test_num_proxies_0_trusts_no_xff_entry(self):
        """DRF semantics: an explicit 0 trusts no proxy, so REMOTE_ADDR wins even with an XFF
        present — the old ``if num_proxies:`` check misread 0 as unset and returned the leftmost."""
        request = self._request(xff="203.0.113.7, 10.0.0.2")
        self.assertEqual(client_ip(request), "10.0.0.9")
