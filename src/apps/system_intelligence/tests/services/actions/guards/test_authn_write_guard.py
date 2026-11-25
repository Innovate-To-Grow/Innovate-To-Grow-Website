"""The assistant's record writes can't move sign-in factors, change Admin status or lock the site out.

An approved DB action used to run ``full_clean()`` and ``save()`` with only the model permission checked. An Admin
approving their own proposals could keep a moved phone verified, verify a phone without a code, move a verified phone
onto another account, forge a verified phone challenge, replace the RSA sign-in key or join a group through its table.
Now contact rows, verification challenges, invitations and the key are read-only to the assistant, many-to-many tables
aren't writable, and Member writes follow ``member_guard``: Admin status changes only on the member's page, and the
lockout rules (no deleting or deactivating your own Admin account or the last active Admin) apply. Proposals are refused
at once, and an action stored before these checks fails at approval with the reason.
"""

from contextlib import contextmanager

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import (
    ContactPhone,
)
from apps.event.tests.helpers import make_admin, make_member, make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.orm import serialize_model_instance

Action = SystemIntelligenceActionRequest
WRITE_REFUSED = "Write access is not allowed for authn.{}."


@contextmanager
def acting_as(user):
    conversation = ChatConversation.objects.create(created_by=user)
    tokens = actions.set_action_context(str(conversation.pk), str(user.pk))
    try:
        yield conversation
    finally:
        actions.reset_action_context(tokens)


class AuthnWriteGuardTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.other_admin = make_superuser(email="other-admin@example.com")
        self.admin = make_admin(email="admin@example.com")
        self.member = make_member(email="member@example.com", first_name="Ada", last_name="Member")
        self.phone = ContactPhone.objects.create(
            member=self.member, phone_number="2095550123", region="1-US", verified=True
        )

    def stored_action(self, user, obj, changes):
        """A pending update as an earlier proposal would have stored it (before these checks existed)."""
        return self.stored(user, Action.ACTION_DB_UPDATE, obj, {"changes": changes})

    def stored(self, user, action_type, obj, payload, *, model=None):
        """A pending action of ``action_type`` on ``obj`` (or, for a create, on ``model``), as stored before."""
        model = model or type(obj)
        conversation = ChatConversation.objects.create(created_by=user)
        return Action.objects.create(
            conversation=conversation,
            created_by=user,
            action_type=action_type,
            target_app_label=model._meta.app_label,
            target_model=model._meta.object_name,
            target_pk=str(obj.pk) if obj is not None else "",
            payload=payload,
            before_snapshot=serialize_model_instance(obj, write=True) if obj is not None else {},
        )

    def assert_failed_with(self, action, message):
        action.refresh_from_db()
        self.assertEqual((action.status, action.error_message), (Action.STATUS_FAILED, message))
