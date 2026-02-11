"""
Serializers for event registration APIs.
"""

from rest_framework import serializers


class EventRegistrationRequestLinkSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EventRegistrationAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField(required=False, allow_null=True)
    question_prompt = serializers.CharField(required=False, allow_blank=True, max_length=500)
    answer_text = serializers.CharField(required=False, allow_blank=True)


class EventRegistrationSubmitSerializer(serializers.Serializer):
    token = serializers.CharField()
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    primary_email = serializers.EmailField(required=False)
    secondary_email = serializers.EmailField(required=False, allow_blank=True)
    primary_email_subscribed = serializers.BooleanField(required=False, default=False)
    secondary_email_subscribed = serializers.BooleanField(required=False, default=False)
    ticket_option_id = serializers.UUIDField(required=False, allow_null=True)
    ticket_label = serializers.CharField(required=False, allow_blank=True, max_length=255)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=32)
    phone_region = serializers.CharField(required=False, allow_blank=True, max_length=20)
    phone_subscribed = serializers.BooleanField(required=False, default=False)
    answers = EventRegistrationAnswerInputSerializer(many=True, required=False)


class EventRegistrationVerifyOTPSerializer(serializers.Serializer):
    token = serializers.CharField()
    code = serializers.CharField(max_length=12)
