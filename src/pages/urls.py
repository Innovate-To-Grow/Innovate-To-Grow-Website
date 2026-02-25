from django.urls import path

from .views import (
    CreatePreviewTokenView,
    GoogleSheetDataView,
    HomePageAPIView,
    HomePageManageDetailView,
    HomePageManageListCreateView,
    HomePageManagePublishView,
    ListPreviewTokensView,
    MediaListView,
    MediaUploadView,
    PageListAPIView,
    PageManageDetailView,
    PageManageListCreateView,
    PageManagePublishView,
    PageRetrieveAPIView,
    PreviewByTokenView,
    PreviewDataView,
    RevokePreviewTokenView,
    SavedComponentDetailView,
    SavedComponentListCreateView,
    ValidatePreviewTokenView,
)

app_name = "pages"

urlpatterns = [
    # pages list (for menu editor)
    path("", PageListAPIView.as_view(), name="page-list"),
    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),
    # page management API (admin CRUD for GrapesJS editor)
    path("manage/", PageManageListCreateView.as_view(), name="page-manage-list"),
    path("manage/<uuid:pk>/", PageManageDetailView.as_view(), name="page-manage-detail"),
    path("manage/<uuid:pk>/publish/", PageManagePublishView.as_view(), name="page-manage-publish"),
    # home page management API
    path("manage/home/", HomePageManageListCreateView.as_view(), name="homepage-manage-list"),
    path("manage/home/<uuid:pk>/", HomePageManageDetailView.as_view(), name="homepage-manage-detail"),
    path("manage/home/<uuid:pk>/publish/", HomePageManagePublishView.as_view(), name="homepage-manage-publish"),
    # preview token validation (legacy cache-based)
    path("preview/validate-token/", ValidatePreviewTokenView.as_view(), name="validate-preview-token"),
    # preview data exchange (admin pushes, preview polls)
    path("preview/data/", PreviewDataView.as_view(), name="preview-data"),
    # shareable preview tokens (database-backed)
    path("preview/tokens/create/", CreatePreviewTokenView.as_view(), name="preview-token-create"),
    path("preview/tokens/", ListPreviewTokensView.as_view(), name="preview-token-list"),
    path("preview/tokens/<str:token>/revoke/", RevokePreviewTokenView.as_view(), name="preview-token-revoke"),
    path("preview/<str:token>/", PreviewByTokenView.as_view(), name="preview-by-token"),
    # saved component library
    path("components/", SavedComponentListCreateView.as_view(), name="component-list"),
    path("components/<uuid:pk>/", SavedComponentDetailView.as_view(), name="component-detail"),
    # media upload and library
    path("upload/", MediaUploadView.as_view(), name="media-upload"),
    path("media/", MediaListView.as_view(), name="media-list"),
    # google sheets
    path("google-sheets/<uuid:sheet_id>/", GoogleSheetDataView.as_view(), name="google-sheet-data"),
    # page detail (path: instead of slug: to support nested slugs like legacy/about)
    # IMPORTANT: Keep this as the LAST pattern since it catches all paths
    path("<path:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
