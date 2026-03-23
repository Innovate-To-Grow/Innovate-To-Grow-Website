"""
Serializer for email subscription.
"""

from rest_framework import serializers

from authn.models import ContactEmail


class SubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    # noinspection PyMethodMayBeStatic
    def validate_email(self, value):
        return value.strip().lower()

    # noinspection PyMethodMayBeStatic
    def create(self, validated_data):
        normalized = validated_data["email"]
        contact, created = ContactEmail.objects.get_or_create(
            email_address=normalized,
            defaults={"subscribe": True, "email_type": "other", "member": None},
        )
        if not created and not contact.subscribe:
            contact.subscribe = True
            contact.save(update_fields=["subscribe", "updated_at"])
        return contact, created
