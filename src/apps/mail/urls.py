from django.urls import path

from .views import LoginLinkView, OneClickUnsubscribeView, ResubscribeView, SesEventWebhookView

app_name = "mail"

urlpatterns = [
    path("login-link/", LoginLinkView.as_view(), name="login-link"),
    # Legacy alias: emails sent before the LoginLinkToken rename point here.
    path("magic-login/", LoginLinkView.as_view(), name="magic-login"),
    path("unsubscribe/<str:token>/", OneClickUnsubscribeView.as_view(), name="oneclick-unsubscribe"),
    path("resubscribe/<str:token>/", ResubscribeView.as_view(), name="resubscribe"),
    path("ses/events/", SesEventWebhookView.as_view(), name="ses-events"),
]
