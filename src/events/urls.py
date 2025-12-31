"""
URL configuration for events app.
"""

from django.urls import path
from .views import EventSyncAPIView, EventRetrieveAPIView

app_name = "events"

urlpatterns = [
    path("sync/", EventSyncAPIView.as_view(), name="event-sync"),
    path("", EventRetrieveAPIView.as_view(), name="event-retrieve"),
]


