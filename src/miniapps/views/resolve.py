from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from miniapps.models import MiniApp


class MiniAppResolveView(APIView):
    """Resolve a URL path to a published mini-app slug and title."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        path = request.query_params.get("path", "")
        if not path:
            return Response({"detail": "path parameter required"}, status=400)

        app = MiniApp.objects.filter(url_path=path, status="published").values("slug", "title").first()

        if not app:
            from django.db.models.functions import Length

            candidates = (
                MiniApp.objects.filter(status="published", url_prefix_match=True)
                .annotate(path_len=Length("url_path"))
                .order_by("-path_len")
                .values("slug", "title", "url_path")
            )
            for candidate in candidates:
                if path == candidate["url_path"] or path.startswith(candidate["url_path"] + "/"):
                    app = candidate
                    break

        if not app:
            return Response({"detail": "Not found"}, status=404)

        return Response({"slug": app["slug"], "title": app["title"], "path": path})
