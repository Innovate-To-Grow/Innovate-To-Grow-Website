"""A campaign-linked Graph failure cannot override conflicting SES evidence for the same original send."""

from django.test import TestCase
from django.utils import timezone

from apps.mail.models import BouncedAddressCampaign, RecipientLog
from apps.mail.services.campaign.content.retry import retry_eligibility_for

from .helpers import make_retry_campaign


class MixedProviderEvidenceTests(TestCase):
    def test_an_unsafe_ses_outcome_vetoes_an_exact_graph_temporary_report(self):
        retry, source, _member, row, _config = make_retry_campaign()
        address = retry.retry_address
        log = RecipientLog.objects.get(campaign=source)
        self.assertIsNotNone(retry_eligibility_for(source, address))

        now = timezone.now()
        for kind, subtype, why in (
            ("Transient", "ContentRejected", "Content rejected"),
            ("Transient", "General", "I am out of the office until Monday"),
            ("Undetermined", "", ""),
            ("Permanent", "General", "550 5.1.1 no such user"),
        ):
            with self.subTest(kind=kind, subtype=subtype):
                # A signed bounce can arrive after the staff review/aggregation and before delivery.
                RecipientLog.objects.filter(pk=log.pk).update(
                    bounced_at=now, bounce_type=kind, bounce_subtype=subtype, diagnostic_code=why
                )
                self.assertIsNone(retry_eligibility_for(source, address))
                RecipientLog.objects.filter(pk=log.pk).update(
                    bounced_at=None, bounce_type="", bounce_subtype="", diagnostic_code=""
                )
                link = BouncedAddressCampaign.objects.create(
                    bounced_address=row,
                    campaign_id=source.pk,
                    source="ses",
                    match="exact",
                    ses_bounced_at=now,
                    ses_bounce_type=kind,
                    ses_bounce_subtype=subtype,
                    ses_diagnostic=why,
                )
                self.assertIsNone(retry_eligibility_for(source, address))
                link.delete()
        self.assertIsNotNone(retry_eligibility_for(source, address))
