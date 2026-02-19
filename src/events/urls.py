"""
URL configuration for events app.
"""

from django.urls import path

from .views import (
    EventRegistrationFormAPIView,
    EventRegistrationRequestLinkAPIView,
    EventRegistrationStatusAPIView,
    EventRegistrationSubmitAPIView,
    EventRegistrationVerifyOTPAPIView,
    EventRetrieveAPIView,
    EventSheetExportAPIView,
    EventSyncAPIView,
)

app_name = "events"

urlpatterns = [
    path("registration/request-link/", EventRegistrationRequestLinkAPIView.as_view(), name="event-registration-request-link"),
    path("registration/form/", EventRegistrationFormAPIView.as_view(), name="event-registration-form"),
    path("registration/submit/", EventRegistrationSubmitAPIView.as_view(), name="event-registration-submit"),
    path("registration/verify-otp/", EventRegistrationVerifyOTPAPIView.as_view(), name="event-registration-verify-otp"),
    path("registration/status/", EventRegistrationStatusAPIView.as_view(), name="event-registration-status"),
    path("sync/", EventSyncAPIView.as_view(), name="event-sync"),
    path("sync/export/", EventSheetExportAPIView.as_view(), name="event-sync-export"),
    path("", EventRetrieveAPIView.as_view(), name="event-retrieve"),
]
