import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import ChatConversation
from apps.system_intelligence.services import actions as system_intelligence_actions
from apps.system_intelligence.services.actions.engine.tool_access import has_chat_grants


def conversations_fragment(request):
    """Return JSON list of conversations for the current user."""
    conversations = ChatConversation.objects.filter(created_by=request.user).only(
        "id", "title", "updated_at", "mode", "required_tool_apps"
    )
    items = []
    for conversation in conversations:
        allowed = has_chat_grants(request.user, conversation.required_tool_apps)
        items.append(
            {
                "id": str(conversation.pk),
                "title": conversation.title if allowed else "Restricted conversation",
                "updated_at": conversation.updated_at.strftime("%b %d, %H:%M"),
                "mode": conversation.mode,
                "restricted": not allowed,
            }
        )
    return JsonResponse({"conversations": items})


def new_conversation_view(request):
    """Create a new conversation and return its ID."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    convo = ChatConversation.objects.create(created_by=request.user)
    return JsonResponse({"id": str(convo.id), "title": convo.title, "mode": convo.mode})


def chat_view(request, conversation_id):
    """Return JSON messages for a conversation."""
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)

    if not has_chat_grants(request.user, convo.required_tool_apps):
        raise PermissionDenied("You do not have access to this conversation.")
    data = []
    for message in convo.messages.prefetch_related("action_requests").order_by("created_at"):
        data.append(
            {
                "id": str(message.id),
                "role": message.role,
                "content": message.content,
                "model_id": message.model_id,
                "created_at": message.created_at.strftime("%b %d, %H:%M"),
                "tool_calls": message.tool_calls or [],
                "token_usage": message.token_usage or {},
                "context_usage": message.context_usage or {},
                "action_requests": [
                    system_intelligence_actions.serialize_action_request(action)
                    for action in message.action_requests.all().order_by("created_at")
                    if user_can_access_app(request.user, action.target_app_label)
                ],
            }
        )
    return JsonResponse(
        {"messages": data, "title": convo.title, "mode": convo.mode, "read_only": convo.required_tool_apps is None}
    )


def chat_delete_view(request, conversation_id):
    """Delete a conversation."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    deleted, _ = ChatConversation.objects.filter(id=conversation_id, created_by=request.user).delete()
    if not deleted:
        return JsonResponse({"error": "Conversation not found"}, status=404)
    return JsonResponse({"ok": True})


def chat_rename_view(request, conversation_id):
    """Rename a conversation."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        convo = ChatConversation.objects.get(id=conversation_id, created_by=request.user)
    except ChatConversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)
    if not has_chat_grants(request.user, convo.required_tool_apps):
        raise PermissionDenied("You do not have access to this conversation.")
    try:
        body = json.loads(request.body)
        new_title = body.get("title", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    if not new_title:
        return JsonResponse({"error": "Title cannot be empty"}, status=400)
    convo.title = new_title[:200]
    convo.auto_title = False
    convo.save(update_fields=["title", "auto_title", "updated_at"])
    return JsonResponse({"ok": True, "title": convo.title})
