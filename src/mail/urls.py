from django.urls import path

from .views import MagicLoginView, OneClickUnsubscribeView, ResubscribeView

app_name = "mail"

urlpatterns = [
    path("magic-login/", MagicLoginView.as_view(), name="magic-login"),
    path("unsubscribe/<str:token>/", OneClickUnsubscribeView.as_view(), name="oneclick-unsubscribe"),
    path("resubscribe/<str:token>/", ResubscribeView.as_view(), name="resubscribe"),
]
