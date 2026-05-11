from django.urls import path

from cms.views.cms import CMSLivePreviewView, CMSPageView, CMSPreviewFetchView
from cms.views.views import EmbedBlockView

urlpatterns = [
    path("live-preview/<uuid:page_id>/", CMSLivePreviewView.as_view(), name="cms-live-preview"),
    path("preview/<str:token>/", CMSPreviewFetchView.as_view(), name="cms-preview-fetch"),
    path("pages/", CMSPageView.as_view(), {"route_path": ""}, name="cms-page-root"),
    path("pages/<path:route_path>/", CMSPageView.as_view(), name="cms-page"),
    path("embed/<slug:embed_slug>/", EmbedBlockView.as_view(), name="cms-embed-block"),
]
