from rest_framework import serializers

from ..models import VerificationRequest


class RequestCodeSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=VerificationRequest.CHANNEL_CHOICES)
    target = serializers.CharField(max_length=255)
    purpose = serializers.CharField(max_length=64, required=False, default="contact_verification")
    context = serializers.JSONField(required=False)


class RequestLinkSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=VerificationRequest.CHANNEL_CHOICES)
    target = serializers.CharField(max_length=255)
    purpose = serializers.CharField(max_length=64, required=False, default="contact_verification")
    base_url = serializers.CharField(
        max_length=512,
        required=False,
        allow_blank=True,
        help_text="Optional base URL to prefix the verification token.",
    )
    context = serializers.JSONField(required=False)


class VerifyCodeSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=VerificationRequest.CHANNEL_CHOICES)
    target = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=12)
    purpose = serializers.CharField(max_length=64, required=False, default="contact_verification")


class SendNotificationSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=VerificationRequest.CHANNEL_CHOICES)
    target = serializers.CharField(max_length=255)
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True)
    message = serializers.CharField()
    provider = serializers.CharField(max_length=64, required=False, allow_blank=True)
    context = serializers.JSONField(required=False)
