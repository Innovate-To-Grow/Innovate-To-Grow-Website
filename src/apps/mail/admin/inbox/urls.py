"""URL routing for inbox admin views."""

from django.contrib import admin
from django.urls import path

from .detail_views import inbox_detail_fragment_view, inbox_detail_view
from .list_views import inbox_fragment_view, inbox_list_view
from .reply_views import inbox_reply_fragment_view, inbox_reply_view


def get_inbox_urls():
    """Return URL patterns for the inbox admin views."""
    return [
        path("mail/inbox/", admin.site.admin_view(inbox_list_view), name="mail_inbox_list"),
        path("mail/inbox/fragment/", admin.site.admin_view(inbox_fragment_view), name="mail_inbox_fragment"),
        path("mail/inbox/<str:uid>/", admin.site.admin_view(inbox_detail_view), name="mail_inbox_detail"),
        path(
            "mail/inbox/<str:uid>/fragment/",
            admin.site.admin_view(inbox_detail_fragment_view),
            name="mail_inbox_detail_fragment",
        ),
        path("mail/inbox/<str:uid>/reply/", admin.site.admin_view(inbox_reply_view), name="mail_inbox_reply"),
        path(
            "mail/inbox/<str:uid>/reply/fragment/",
            admin.site.admin_view(inbox_reply_fragment_view),
            name="mail_inbox_reply_fragment",
        ),
    ]
