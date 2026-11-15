from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign


class CampaignActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_a_sent_campaign_links_to_its_monitoring(self):
        campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")

        response = self.client.get(reverse("admin:mail_emailcampaign_delivery_monitoring_action", args=[campaign.pk]))

        self.assertRedirects(
            response, reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]), fetch_redirect_response=False
        )
