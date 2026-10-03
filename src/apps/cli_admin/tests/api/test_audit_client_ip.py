"""Tests for apps.cli_admin.views.helpers.client_ip (NUM_PROXIES-aware audit IP)."""

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.cli_admin.views.helpers import client_ip


class AuditClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, xff=None, remote_addr="10.0.0.9"):
        meta = {"REMOTE_ADDR": remote_addr}
        if xff is not None:
            meta["HTTP_X_FORWARDED_FOR"] = xff
        return self.factory.get("/", **meta)

    @override_settings(NUM_PROXIES=1)
    def test_trusted_proxy_ignores_client_supplied_leftmost_hops(self):
        # Production shape: the ALB appends the real peer as the rightmost entry; everything to its left
        # is attacker-controlled and must not reach the audit row.
        request = self._request(xff="198.51.100.99, 192.0.2.1, 203.0.113.7")
        self.assertEqual(client_ip(request), "203.0.113.7")

    @override_settings(NUM_PROXIES=1)
    def test_trusted_proxy_without_spoofing_returns_the_single_entry(self):
        self.assertEqual(client_ip(self._request(xff="203.0.113.7")), "203.0.113.7")

    @override_settings(NUM_PROXIES=0)
    def test_zero_proxies_trusts_no_forwarded_entry(self):
        request = self._request(xff="198.51.100.99")
        self.assertEqual(client_ip(request), "10.0.0.9")

    @override_settings(NUM_PROXIES=None)
    def test_unset_num_proxies_falls_back_to_leftmost_entry(self):
        # Local / test: no proxy in front, so the leftmost hop is the best available signal.
        request = self._request(xff="203.0.113.7, 10.0.0.1")
        self.assertEqual(client_ip(request), "203.0.113.7")

    def test_no_forwarded_header_returns_remote_addr(self):
        self.assertEqual(client_ip(self._request()), "10.0.0.9")

    def test_blank_forwarded_header_falls_back_to_remote_addr(self):
        self.assertEqual(client_ip(self._request(xff="  ,  ")), "10.0.0.9")

    def test_empty_remote_addr_is_none_not_empty_string(self):
        self.assertIsNone(client_ip(self._request(remote_addr="")))

    def test_missing_remote_addr_is_none(self):
        request = self.factory.get("/")
        del request.META["REMOTE_ADDR"]
        self.assertIsNone(client_ip(request))
