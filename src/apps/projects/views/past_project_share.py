from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from ..models import PastProjectShare
from ..serializers import PastProjectShareSerializer
from ..throttles import PastProjectShareRateThrottle


class PastProjectShareCreateAPIView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PastProjectShareSerializer
    throttle_classes = [PastProjectShareRateThrottle]


class PastProjectShareDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PastProjectShareSerializer
    queryset = PastProjectShare.objects.all()
    lookup_field = "pk"
