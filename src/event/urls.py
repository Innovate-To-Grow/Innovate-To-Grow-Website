from django.urls import path

from event.views import (
    CurrentEventScheduleView,
    EventRegistrationCreateView,
    EventRegistrationOptionsView,
    MyTicketsView,
    ResendTicketEmailView,
    TicketAutoLoginView,
)

app_name = "event"

urlpatterns = [
    path("schedule/", CurrentEventScheduleView.as_view(), name="schedule"),
    path("registration-options/", EventRegistrationOptionsView.as_view(), name="registration-options"),
    path("registrations/", EventRegistrationCreateView.as_view(), name="registration-create"),
    path("my-tickets/", MyTicketsView.as_view(), name="my-tickets"),
    path("my-tickets/<uuid:pk>/resend-email/", ResendTicketEmailView.as_view(), name="resend-ticket-email"),
    path("ticket-login/", TicketAutoLoginView.as_view(), name="ticket-login"),
]
