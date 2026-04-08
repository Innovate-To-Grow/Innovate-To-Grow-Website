from django.urls import path

from .views import MagicLoginView, OneClickUnsubscribeView

app_name = "mail"

urlpatterns = [
    path("magic-login/", MagicLoginView.as_view(), name="magic-login"),
    path("unsubscribe/<str:token>/", OneClickUnsubscribeView.as_view(), name="oneclick-unsubscribe"),
]
