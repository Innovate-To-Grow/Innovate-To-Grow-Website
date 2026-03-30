from django.urls import path

from cms.views.cms import CMSLivePreviewView, CMSPageView, CMSPreviewFetchView

urlpatterns = [
    path("live-preview/<uuid:page_id>/", CMSLivePreviewView.as_view(), name="cms-live-preview"),
    path("preview/<str:token>/", CMSPreviewFetchView.as_view(), name="cms-preview-fetch"),
    path("pages/", CMSPageView.as_view(), {"route_path": ""}, name="cms-page-root"),
    path("pages/<path:route_path>/", CMSPageView.as_view(), name="cms-page"),
]
