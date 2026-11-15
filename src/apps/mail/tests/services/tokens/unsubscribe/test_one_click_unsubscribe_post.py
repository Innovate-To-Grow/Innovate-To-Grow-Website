import uuid

from django.core import signing

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.unsubscribe import (
    _SALT,
)
from apps.mail.tests.services.tokens.unsubscribe.test_oneclick_unsubscribe import (
    _RESUBSCRIBE_FORM,
    _UnsubscribeTestBase,
)


class OneClickUnsubscribePostTests(_UnsubscribeTestBase):
    def test_post_unsubscribes_every_address_of_the_member(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertEqual(
            self._flags(),
            {"unsub@example.com": False, "unsub-2@example.com": False, "unsub-3@example.com": False},
        )

    def test_post_leaves_other_members_untouched(self):
        other = make_member(email="bystander@example.com")

        self.client.post(self.url)

        self.assertEqual(self._flags(other), {"bystander@example.com": True})

    def test_post_does_not_delete_member(self):
        self.client.post(self.url)
        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())

    def test_one_click_post_never_reads_the_body(self):
        """RFC 8058 POSTs, the confirmation form and odd clients all work: the token is the whole request."""
        bodies = {
            "rfc8058 form body": {
                "data": "List-Unsubscribe=One-Click",
                "content_type": "application/x-www-form-urlencoded",
            },
            "multipart form": {"data": {"List-Unsubscribe": "One-Click"}},
            "multipart without boundary": {"data": "List-Unsubscribe=One-Click", "content_type": "multipart/form-data"},
            "json": {"data": '{"List-Unsubscribe": "One-Click"}', "content_type": "application/json"},
            "malformed json": {"data": "{not json", "content_type": "application/json"},
            "text/plain": {"data": "List-Unsubscribe=One-Click", "content_type": "text/plain"},
            "empty body": {},
        }
        for index, (label, kwargs) in enumerate(bodies.items()):
            with self.subTest(body=label):
                member, token = self._subscribed_member_with_token(f"body-{index}@example.com")

                response = self.client.post(f"/mail/unsubscribe/{token}/", **kwargs)

                self.assertEqual(response.status_code, 200)
                self.assertFalse(self._member_is_subscribed(member))

    def test_unusual_accept_header_or_format_param_still_unsubscribes(self):
        cases = {
            "accept text/plain": ({}, {"HTTP_ACCEPT": "text/plain"}),
            "accept xhtml only": ({}, {"HTTP_ACCEPT": "application/xhtml+xml"}),
            "format=json": ({"format": "json"}, {}),
            "format=unknown": ({"format": "foo"}, {}),
        }
        for index, (label, (query, headers)) in enumerate(cases.items()):
            with self.subTest(case=label):
                member, token = self._subscribed_member_with_token(f"accept-{index}@example.com")
                url = f"/mail/unsubscribe/{token}/"
                if query:
                    url += "?" + "&".join(f"{key}={value}" for key, value in query.items())

                self.assertEqual(self.client.get(url, **headers).status_code, 200)
                response = self.client.post(url, **headers)

                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])
                self.assertFalse(self._member_is_subscribed(member))

    def test_replay_is_idempotent(self):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "You've been unsubscribed")
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_footer_click_after_header_one_click_gets_success(self):
        self.client.post(self.url)  # Gmail's one-click header

        get_response = self.client.get(self.url)
        post_response = self.client.post(self.url)

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "You've been unsubscribed")
        self.assertEqual(post_response.status_code, 200)

    def test_already_unsubscribed_member_gets_success(self):
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You've been unsubscribed")

    def test_deactivated_member_can_unsubscribe(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))
        # The resubscribe link rejects inactive members, so none is offered.
        self.assertIsNone(_RESUBSCRIBE_FORM.search(response.content.decode()))

    def test_invalid_token_returns_400(self):
        response = self.client.post("/mail/unsubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_wrong_salt_token_returns_400(self):
        bad_token = signing.dumps({"member_id": str(self.member.pk)}, salt="wrong-salt")
        response = self.client.post(f"/mail/unsubscribe/{bad_token}/")
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_member_returns_400(self):
        fake_token = signing.dumps({"member_id": str(uuid.uuid4())}, salt=_SALT)
        response = self.client.post(f"/mail/unsubscribe/{fake_token}/")
        self.assertEqual(response.status_code, 400)

    def test_token_payload_and_salt_are_unchanged(self):
        """Links already in inboxes carry exactly this payload under this salt."""
        legacy = signing.dumps({"member_id": str(self.member.pk)}, salt="rfc8058-one-click-unsubscribe", compress=True)

        response = self.client.post(f"/mail/unsubscribe/{legacy}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_responses_are_never_cached(self):
        responses = {
            "get": self.client.get(self.url),
            "post": self.client.post(self.url),
            "invalid": self.client.post("/mail/unsubscribe/garbage-token/"),
        }
        for label, response in responses.items():
            with self.subTest(response=label):
                self.assertIn("no-store", response["Cache-Control"])
