from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from miniapps.models import MiniApp
from miniapps.services.renderer import render_miniapp_document


class MiniAppCodeView(APIView):
    """Serves the full HTML document for rendering in a sandboxed iframe."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(xframe_options_exempt)
    def get(self, request, app_slug):
        app = MiniApp.objects.filter(slug=app_slug, status="published").first()
        if not app:
            return HttpResponse("<h1>Not Found</h1>", status=404, content_type="text/html")

        current_path = request.query_params.get("path", app.url_path)
        html = render_miniapp_document(app, current_path=current_path)
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["Access-Control-Allow-Origin"] = "*"
        response["Cache-Control"] = "no-cache"
        return response
