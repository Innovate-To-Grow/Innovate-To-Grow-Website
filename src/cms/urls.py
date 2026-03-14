from django.urls import path

from .views import CMSPageView

urlpatterns = [
    path("pages/<path:route_path>/", CMSPageView.as_view(), name="cms-page"),
]
