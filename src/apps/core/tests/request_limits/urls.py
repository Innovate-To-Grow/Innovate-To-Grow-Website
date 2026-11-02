"""Views in each test scope, for the middleware tests (``helpers.limiter_on`` routes to them)."""

from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.urls import path
from django.views import View
from django.views.decorators.csrf import csrf_exempt


def _view(scope, status=200):
    @csrf_exempt
    def view(request):
        return JsonResponse({"ok": True}, status=status)

    view.rate_limit_scope = scope
    return view


@csrf_exempt
def broken(request):
    raise RuntimeError("view failed")


def exempt_view(request):
    return HttpResponse("exempt")


exempt_view.rate_limit_exempt = "Test exemption."


class MethodScopedView(View):
    rate_limit_scope = {"GET": "t-p1", "*": "t-p3"}

    def get(self, request):
        return HttpResponse("read")

    def post(self, request):
        return HttpResponse("write")


@csrf_exempt
def unscoped(request):
    return HttpResponse("fallback")


urlpatterns = [
    path("p0/", _view("t-p0"), name="p0"),
    path("p1/", _view("t-p1"), name="p1"),
    path("p2/", _view("t-p2"), name="p2"),
    path("p3/", _view("t-p3"), name="p3"),
    path("fixed/", _view("t-fixed"), name="fixed"),
    path("p0-refused/", _view("t-p0", status=429), name="p0-refused"),
    path("p1-error/", _view("t-p1", status=503), name="p1-error"),
    path("broken/", broken, name="broken"),
    path("exempt/", exempt_view, name="exempt"),
    path("methods/", csrf_exempt(MethodScopedView.as_view()), name="methods"),
    path("unscoped/", unscoped, name="unscoped"),
]


def not_found(request, exception=None):
    return HttpResponseNotFound("missing")


handler404 = not_found
