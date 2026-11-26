"""
Authn app admin configuration.

Registers all authn models with Django admin for user management:
- members.member: the Member admin (its actions, custom views and lockout rules are mixins)
- members.contact: ContactEmail, ContactPhone admins; members.inlines: their rows on a member's page
- members.import_: member import pages and the read-only history of imports
- members.primary_switch: the Switch primary email page; members.shared: filters, search, labels, sign-in warning
- security: AdminInvitation, RSAKeypair and SendVerificationConfig (a core model owned by this feature) admins
"""

from django.contrib import admin
from django.contrib.auth.models import Group

from apps.authn.services.members.sheet_sync.admin import MemberSheetSyncConfigAdmin, MemberSheetSyncLogAdmin

from .members.contact import ContactEmailAdmin, ContactPhoneAdmin
from .members.import_.batch import MemberImportBatchAdmin
from .members.member.admin import MemberAdmin
from .security.invitation import AdminInvitationAdmin
from .security.rsa_keypair import RSAKeypairAdmin
from .security.send_verification import SendVerificationConfigAdmin

admin.site.unregister(Group)

__all__ = [
    # Member
    "MemberAdmin",
    # Contact
    "ContactEmailAdmin",
    "ContactPhoneAdmin",
    # Invitation
    "AdminInvitationAdmin",
    # Member imports (history)
    "MemberImportBatchAdmin",
    # Security
    "RSAKeypairAdmin",
    "SendVerificationConfigAdmin",
    # Sheet Sync
    "MemberSheetSyncConfigAdmin",
    "MemberSheetSyncLogAdmin",
]
