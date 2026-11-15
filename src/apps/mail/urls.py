from django.urls import path

from .views import (
    LoginLinkView,
    OneClickUnsubscribeView,
    RegisterLinkView,
    ResubscribeView,
    SesEventWebhookView,
    SmsLinkView,
)

app_name = "mail"

urlpatterns = [
    path("login-link/", LoginLinkView.as_view(), name="login-link"),
    # Legacy alias: emails sent before the LoginLinkToken rename point here.
    path("magic-login/", LoginLinkView.as_view(), name="magic-login"),
    path("unsubscribe/<str:token>/", OneClickUnsubscribeView.as_view(), name="oneclick-unsubscribe"),
    path("resubscribe/<str:token>/", ResubscribeView.as_view(), name="resubscribe"),
    path("ses/events/", SesEventWebhookView.as_view(), name="ses-events"),
    # The SMS short links (/l/<token> in the SPA) and where the short /register link leads.
    path("sms-link/", SmsLinkView.as_view(), name="sms-link"),
    path("register-link/", RegisterLinkView.as_view(), name="register-link"),
]
