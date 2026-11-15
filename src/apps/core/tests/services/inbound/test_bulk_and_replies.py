"""List, bulk and marketing mail against a person's reply (pure, on the synthetic samples): a list's distribution and
the weak bulk signals, Exchange's bulk complaint level and its threshold, and a reply to the site's mail, which weak
signals alone never make bulk (a person answering a campaign from a CRM tool), while a list's distribution still
does (decision to confirm) and spam stays spam."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import REPLY_HINT, auth_summary, classify
from apps.core.services.email.inbound.bulk import bulk_complaint_level

from . import samples
from .test_classify import OWN, evidence


def verdict_of(raw: bytes, *, replies: bool, **thresholds):
    return classify(samples.evidence_of(raw, replies_to_site_mail=replies), own_addresses=OWN, **thresholds)


class MarketingTests(SimpleTestCase):
    def test_a_marketing_newsletter_is_list_mail_with_every_signal(self):
        verdict = verdict_of(samples.newsletter(), replies=False)

        self.assertEqual((verdict.classification, verdict.subtype), ("bulk", "list"))
        self.assertEqual(
            verdict.signals,
            ("list-id", "list-unsubscribe", "list-unsubscribe-post", "x-sg-eid", "precedence_bulk", "bcl_8"),
        )

    def test_the_bulk_complaint_level_alone_counts_from_the_threshold(self):
        at = verdict_of(samples.bulk_by_bcl_only(7), replies=False)
        below = verdict_of(samples.bulk_by_bcl_only(6), replies=False)
        stricter = verdict_of(samples.bulk_by_bcl_only(6), replies=False, bcl_threshold=5)
        laxer = verdict_of(samples.bulk_by_bcl_only(8), replies=False, bcl_threshold=9)

        self.assertEqual((at.classification, at.subtype, at.signals), ("bulk", "newsletter", ("bcl_7",)))
        self.assertEqual((below.classification, laxer.classification), ("human", "human"))
        self.assertEqual(stricter.classification, "bulk")

    def test_the_highest_bulk_complaint_level_counts_and_garbage_is_ignored(self):
        self.assertEqual(bulk_complaint_level({"x-microsoft-antispam": ["BCL:2;", "ARA:1;BCL:7;", "BCL:x;"]}), 7)
        self.assertIsNone(bulk_complaint_level({"x-microsoft-antispam": ["ARA:13230040;"]}))
        self.assertIsNone(bulk_complaint_level({}))

    def test_the_bulk_complaint_level_is_shown_with_the_authentication_results(self):
        self.assertEqual(auth_summary({"x-microsoft-antispam": ["BCL:7;"]}), {"bcl": 7})

    def test_subtypes_name_what_sent_it(self):
        provider = classify(evidence({"X-Mailgun-Sid": "x"}, from_address="noreply@x.example"), own_addresses=OWN)
        noreply = classify(evidence({"Precedence": "bulk"}, from_address="noreply@x.example"), own_addresses=OWN)
        listed = classify(evidence({"Precedence": "list"}), own_addresses=OWN)

        self.assertEqual((provider.subtype, noreply.subtype, listed.subtype), ("newsletter", "noreply", "list"))
        self.assertEqual(listed.signals, ("precedence_list",))


class ReplyToSiteMailTests(SimpleTestCase):
    def test_a_person_answering_the_campaign_from_a_crm_about_judging_is_a_person(self):
        verdict = verdict_of(samples.crm_reply_about_judging(), replies=True)

        self.assertEqual(verdict.classification, "human")
        self.assertFalse(verdict.automated)
        self.assertEqual(verdict.hints[0], REPLY_HINT)
        self.assertIn("bulk_headers_on_reply", verdict.hints)
        for signal in ("list-unsubscribe", "x-sfdc-lk", "x-sfdc-user", "bcl_7"):
            self.assertIn(signal, verdict.hints)

    def test_the_same_message_answering_nothing_the_site_sent_is_bulk(self):
        verdict = verdict_of(samples.crm_reply_about_judging(reply=False), replies=False)

        self.assertEqual((verdict.classification, verdict.subtype), ("bulk", "list"))
        self.assertNotIn(REPLY_HINT, verdict.hints)

    def test_a_reply_through_a_mailing_list_stays_list_mail(self):
        # Decision to confirm: a reply to the site's mail overrides only the weak bulk signals, not a list's distribution.
        verdict = verdict_of(samples.mailing_list_reply(), replies=True)

        self.assertEqual((verdict.classification, verdict.subtype), ("bulk", "list"))
        self.assertEqual(verdict.signals[:3], ("list-id", "list-post", "precedence_list"))
        self.assertEqual(verdict.hints, (REPLY_HINT,))

    def test_each_weak_signal_alone_is_overridden_by_a_reply(self):
        for headers in (
            {"List-Unsubscribe": "<mailto:leave@x.example>"},
            {"X-HubSpot-Email": "1"},
            {"Precedence": "bulk"},
            {"X-Microsoft-Antispam": "BCL:9;"},
        ):
            with self.subTest(headers):
                self.assertEqual(classify(evidence(headers), own_addresses=OWN).classification, "bulk")
                reply = classify(evidence(headers, replies_to_site_mail=True), own_addresses=OWN)
                self.assertEqual(reply.classification, "human")
        noreply = classify(evidence(from_address="no-reply@x.example", replies_to_site_mail=True), own_addresses=OWN)
        self.assertEqual(noreply.classification, "human")

    def test_a_plain_reply_has_only_the_reply_hint(self):
        verdict = classify(evidence(text_head="Count me in!", replies_to_site_mail=True), own_addresses=OWN)

        self.assertEqual((verdict.classification, verdict.hints), ("human", (REPLY_HINT,)))

    def test_a_reply_is_still_spam_by_exchanges_verdicts(self):
        verdict = classify(
            evidence(
                {"X-MS-Exchange-Organization-SCL": "9", "List-Unsubscribe": "<mailto:leave@x.example>"},
                replies_to_site_mail=True,
            ),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype), ("spam", "scl"))
        self.assertIn(REPLY_HINT, verdict.hints)

    def test_a_calendar_answer_to_the_sites_invitation_stays_system_mail(self):
        verdict = classify(
            evidence(subject="Accepted: Judges' briefing", has_calendar=True, replies_to_site_mail=True),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype), ("system", "calendar"))
