"""
URL configuration for events app.
"""

from django.urls import path

from .views import EventRetrieveAPIView, EventSheetExportAPIView, EventSyncAPIView

app_name = "events"

urlpatterns = [
    path("sync/", EventSyncAPIView.as_view(), name="event-sync"),
    path("sync/export/", EventSheetExportAPIView.as_view(), name="event-sync-export"),
    path("", EventRetrieveAPIView.as_view(), name="event-retrieve"),
]
