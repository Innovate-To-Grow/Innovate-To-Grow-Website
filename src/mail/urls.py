"""
URL configuration for mail app.
"""

from django.urls import path

from .views import SNSWebhookView

app_name = "mail"

urlpatterns = [
    path("sns/webhook/", SNSWebhookView.as_view(), name="sns-webhook"),
]
