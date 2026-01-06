"""
URL configuration for events app.
"""

from django.urls import path
from .views import (
    EventSyncAPIView,
    EventRetrieveAPIView,
    EventArchiveRetrieveAPIView,
    PastEventsListAPIView,
)

app_name = "events"

urlpatterns = [
    path("sync/", EventSyncAPIView.as_view(), name="event-sync"),
    path("", EventRetrieveAPIView.as_view(), name="event-retrieve"),
    path("archive/<slug:slug>/", EventArchiveRetrieveAPIView.as_view(), name="event-archive-retrieve"),
    path("past-events-list/", PastEventsListAPIView.as_view(), name="past-events-list"),
]


