from django.urls import path

from apps.system_intelligence.views import PublicAssistantChatView, PublicAssistantConfigView

app_name = "system_intelligence"

urlpatterns = [
    path("chat/", PublicAssistantChatView.as_view(), name="public-assistant-chat"),
    path("config/", PublicAssistantConfigView.as_view(), name="public-assistant-config"),
]
