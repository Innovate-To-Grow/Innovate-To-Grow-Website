from rest_framework import status
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analytics.models import PageView
from analytics.serializers import PageViewCreateSerializer


class PageViewCreateView(CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = PageViewCreateSerializer
    queryset = PageView.objects.all()

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def perform_create(self, serializer):
        request = self.request
        member = request.user if request.user.is_authenticated else None
        serializer.save(
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            member=member,
            session_key=request.session.session_key or "",
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(status=status.HTTP_201_CREATED)
