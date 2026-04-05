from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.services.import_excel import import_projects_from_excel


class ProjectImportAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def post(self, request):
        excel_file = request.FILES.get("file")
        if not excel_file:
            return Response({"detail": "No file provided."}, status=400)

        if not excel_file.name.endswith(".xlsx"):
            return Response({"detail": "Only .xlsx files are supported."}, status=400)

        try:
            stats = import_projects_from_excel(excel_file)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        return Response(stats)
