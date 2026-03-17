from django.urls import path

from event.views import (
    EventRegistrationCreateView,
    EventRegistrationOptionsView,
    MyTicketsView,
    ResendTicketEmailView,
)

app_name = "event"

urlpatterns = [
    path("registration-options/", EventRegistrationOptionsView.as_view(), name="registration-options"),
    path("registrations/", EventRegistrationCreateView.as_view(), name="registration-create"),
    path("my-tickets/", MyTicketsView.as_view(), name="my-tickets"),
    path("my-tickets/<uuid:pk>/resend-email/", ResendTicketEmailView.as_view(), name="resend-ticket-email"),
]
