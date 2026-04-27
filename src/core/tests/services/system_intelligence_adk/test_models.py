import uuid

from django.test import TestCase

from core.models import ProjectControlModel
from core.models.base.system_intelligence import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
    SystemIntelligenceExport,
)
from event.tests.helpers import make_superuser


class SystemIntelligenceProjectControlModelTests(TestCase):
    def test_system_intelligence_models_use_project_control_fields(self):
        admin_user = make_superuser()
        conversation = ChatConversation.objects.create(created_by=admin_user)
        message = ChatMessage.objects.create(
            conversation=conversation,
            role="user",
            content="Hello",
        )
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=conversation,
            assistant_message=message,
            created_by=admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            title="Update source",
        )
        config = SystemIntelligenceConfig.objects.create(name="System Intelligence", is_active=True)
        export = SystemIntelligenceExport.objects.create(
            conversation=conversation,
            created_by=admin_user,
            title="Export",
            filename="export.xlsx",
            file="system_intelligence_exports/test/export.xlsx",
        )

        for model in (
            ChatConversation,
            ChatMessage,
            SystemIntelligenceActionRequest,
            SystemIntelligenceConfig,
            SystemIntelligenceExport,
        ):
            self.assertTrue(issubclass(model, ProjectControlModel))

        for obj in (conversation, message, action, config, export):
            self.assertIsInstance(obj.id, uuid.UUID)
            self.assertIsNotNone(obj.created_at)
            self.assertIsNotNone(obj.updated_at)

    def test_system_intelligence_config_load_keeps_unsaved_default_without_pk(self):
        config = SystemIntelligenceConfig.load()

        self.assertIsNone(config.pk)
        self.assertTrue(config._state.adding)
