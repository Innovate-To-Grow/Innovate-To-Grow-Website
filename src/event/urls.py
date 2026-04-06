from django.urls import path

from event.views import (
    CheckInScanView,
    CheckInStatusView,
    CurrentEventScheduleView,
    CurrentProjectsAPIView,
    EventRegistrationCreateView,
    EventRegistrationOptionsView,
    MyTicketsView,
    ProjectImportAPIView,
    ResendTicketEmailView,
    SendPhoneCodeView,
    TicketAutoLoginView,
    VerifyPhoneCodeView,
)

app_name = "event"

urlpatterns = [
    path("projects/", CurrentProjectsAPIView.as_view(), name="current-projects"),
    path("import/", ProjectImportAPIView.as_view(), name="project-import"),
    path("schedule/", CurrentEventScheduleView.as_view(), name="schedule"),
    path("registration-options/", EventRegistrationOptionsView.as_view(), name="registration-options"),
    path("registrations/", EventRegistrationCreateView.as_view(), name="registration-create"),
    path("my-tickets/", MyTicketsView.as_view(), name="my-tickets"),
    path("my-tickets/<uuid:pk>/resend-email/", ResendTicketEmailView.as_view(), name="resend-ticket-email"),
    path("send-phone-code/", SendPhoneCodeView.as_view(), name="send-phone-code"),
    path("verify-phone-code/", VerifyPhoneCodeView.as_view(), name="verify-phone-code"),
    path("check-in/<uuid:checkin_id>/scan/", CheckInScanView.as_view(), name="checkin-scan"),
    path("check-in/<uuid:checkin_id>/status/", CheckInStatusView.as_view(), name="checkin-status"),
    path("ticket-login/", TicketAutoLoginView.as_view(), name="ticket-login"),
]
