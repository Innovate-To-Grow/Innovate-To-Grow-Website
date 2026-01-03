from django.urls import path

from .views import (
    RequestCodeAPIView,
    RequestLinkAPIView,
    SendNotificationAPIView,
    VerifyCodeAPIView,
    VerifyLinkAPIView,
)

app_name = "notify"

urlpatterns = [
    path("request-code/", RequestCodeAPIView.as_view(), name="request-code"),
    path("request-link/", RequestLinkAPIView.as_view(), name="request-link"),
    path("verify-code/", VerifyCodeAPIView.as_view(), name="verify-code"),
    path("verify-link/<str:token>/", VerifyLinkAPIView.as_view(), name="verify-link"),
    path("send/", SendNotificationAPIView.as_view(), name="send-notification"),
]
