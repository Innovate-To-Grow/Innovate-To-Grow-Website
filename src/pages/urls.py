from django.urls import path

from .views import (
    FormSubmissionCreateAPIView,
    FormSubmissionListAPIView,
    GoogleSheetDataView,
    HomePageAPIView,
    MediaListView,
    MediaUploadView,
    PageListAPIView,
    PageRetrieveAPIView,
    PreviewDataView,
    UniformFormRetrieveAPIView,
    ValidatePreviewTokenView,
)

app_name = "pages"

urlpatterns = [
    # pages list (for menu editor)
    path("", PageListAPIView.as_view(), name="page-list"),
    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),
    # preview token validation
    path("preview/validate-token/", ValidatePreviewTokenView.as_view(), name="validate-preview-token"),
    # preview data exchange (admin pushes, preview polls)
    path("preview/data/", PreviewDataView.as_view(), name="preview-data"),
    # media upload and library
    path("upload/", MediaUploadView.as_view(), name="media-upload"),
    path("media/", MediaListView.as_view(), name="media-list"),
    # forms
    path("forms/<slug:slug>/", UniformFormRetrieveAPIView.as_view(), name="form-detail"),
    path("forms/<slug:slug>/submit/", FormSubmissionCreateAPIView.as_view(), name="form-submit"),
    path("forms/<slug:form_slug>/submissions/", FormSubmissionListAPIView.as_view(), name="form-submissions"),
    # google sheets
    path("google-sheets/<uuid:sheet_id>/", GoogleSheetDataView.as_view(), name="google-sheet-data"),
    # page detail (path: instead of slug: to support nested slugs like legacy/about)
    path("<path:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
