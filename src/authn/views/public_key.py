"""
Public key API for RSA encryption.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.services import get_public_key_pem


class PublicKeyView(APIView):
    """
    API endpoint to retrieve the current public key for password encryption.
    """

    def get(self, request):
        """
        Get the current public key PEM and key ID.
        The client should use this to encrypt passwords before sending.
        """
        try:
            public_key_pem, key_id = get_public_key_pem()
            return Response(
                {
                    "public_key": public_key_pem,
                    "key_id": key_id,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to retrieve public key: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
