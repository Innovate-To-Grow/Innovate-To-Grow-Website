from django.test import TestCase

from core.models import AWSCredentialConfig
from core.models.base.system_intelligence import ChatConversation, SystemIntelligenceConfig
from event.tests.helpers import make_superuser


class SystemIntelligenceAdminBase(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            system_prompt="Use tools.",
        )
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)
