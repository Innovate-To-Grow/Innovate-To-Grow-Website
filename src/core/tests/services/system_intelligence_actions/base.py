from django.core.cache import cache
from django.test import TestCase

from core.models.base.system_intelligence import ChatConversation
from core.services import system_intelligence_actions as actions
from event.tests.helpers import make_superuser


class SystemIntelligenceActionBase(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.conversation = ChatConversation.objects.create(created_by=self.admin_user)
        self.context_tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))

    def tearDown(self):
        actions.reset_action_context(self.context_tokens)
