from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from ..models import Project
from ..serializers import ProjectDetailSerializer


class ProjectDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProjectDetailSerializer
    queryset = Project.objects.select_related("semester")
    lookup_field = "pk"
