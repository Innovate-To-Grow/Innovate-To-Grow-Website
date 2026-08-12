from rest_framework import serializers


class TokenExchangeSerializer(serializers.Serializer):
    """Validates the OAuth token-exchange POST body."""

    grant_type = serializers.CharField()
    code = serializers.CharField()
    code_verifier = serializers.CharField()
    redirect_uri = serializers.CharField()
    client_id = serializers.CharField()
