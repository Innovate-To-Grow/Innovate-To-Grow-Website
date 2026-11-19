"""Shared fixtures for a fully eligible, provenance-bound one-address retry."""

from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign, RecipientLog


def make_retry_campaign(*, address="retry-worker@example.com", config=None):
    config = config or EmailServiceConfig.objects.create(
        name="Retry snapshot", is_active=True, provider="ses", from_email="snapshot@example.org", from_name="I2G"
    )
    member = make_member(email=address, first_name="Retry", last_name="Recipient")
    source = EmailCampaign.objects.create(
        name="Source campaign",
        subject="Original",
        body="Body",
        audience_type="manual",
        manual_emails=address,
        status="sent",
        sent_at=timezone.now(),
    )
    RecipientLog.objects.create(
        campaign=source,
        member=member,
        email_address=address,
        status="bounced",
        sent_at=timezone.now(),
    )
    row = BouncedAddress.objects.create(
        address=address,
        soft_count=1,
        category_counts={"transient": 1},
    )
    BouncedAddressCampaign.objects.create(
        bounced_address=row,
        campaign_id=source.pk,
        source=BouncedAddressCampaign.Source.GRAPH,
        match=BouncedAddressCampaign.Match.EXACT,
        bounce_count=1,
        graph_category_counts={"transient": 1},
        first_at=timezone.now(),
        last_at=timezone.now(),
    )
    retry = EmailCampaign.objects.create(
        name="Retry campaign",
        subject="Retry",
        body="Body",
        audience_type="manual",
        manual_emails=address,
        retry_source_campaign=source,
        retry_address=address,
        retry_email_config=config,
        retry_sending_provider=config.provider,
        retry_from_email=config.from_email,
        retry_from_name=config.from_name,
        retry_configuration_set="retry-config-set",
    )
    return retry, source, member, row, config
