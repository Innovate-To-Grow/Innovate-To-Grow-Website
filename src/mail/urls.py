from django.urls import path

from .views import MagicLoginView

app_name = "mail"

urlpatterns = [
    path("magic-login/", MagicLoginView.as_view(), name="magic-login"),
]
