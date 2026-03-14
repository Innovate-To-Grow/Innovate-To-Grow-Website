from django.urls import path

from .views import CMSPageView, CMSPreviewFetchView

urlpatterns = [
    path("preview/<str:token>/", CMSPreviewFetchView.as_view(), name="cms-preview-fetch"),
    path("pages/", CMSPageView.as_view(), {"route_path": ""}, name="cms-page-root"),
    path("pages/<path:route_path>/", CMSPageView.as_view(), name="cms-page"),
]
