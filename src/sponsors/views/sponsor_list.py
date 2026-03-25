from itertools import groupby

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Sponsor
from ..serializers import SponsorSerializer


class SponsorListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sponsors = Sponsor.objects.all()
        grouped = []
        for year, group in groupby(sponsors, key=lambda s: s.year):
            grouped.append(
                {
                    "year": year,
                    "sponsors": SponsorSerializer(list(group), many=True, context={"request": request}).data,
                }
            )
        return Response(grouped)
