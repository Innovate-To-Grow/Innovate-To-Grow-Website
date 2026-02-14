from django.urls import path

from .views import (
    FormSubmissionCreateAPIView,
    FormSubmissionListAPIView,
    HomePageAPIView,
    MediaListView,
    MediaUploadView,
    PageListAPIView,
    PageRetrieveAPIView,
    UniformFormRetrieveAPIView,
)

app_name = "pages"

urlpatterns = [
    # pages list (for menu editor)
    path("", PageListAPIView.as_view(), name="page-list"),
    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),
    # media upload and library
    path("upload/", MediaUploadView.as_view(), name="media-upload"),
    path("media/", MediaListView.as_view(), name="media-list"),
    # forms
    path("forms/<slug:slug>/", UniformFormRetrieveAPIView.as_view(), name="form-detail"),
    path("forms/<slug:slug>/submit/", FormSubmissionCreateAPIView.as_view(), name="form-submit"),
    path("forms/<slug:form_slug>/submissions/", FormSubmissionListAPIView.as_view(), name="form-submissions"),
    # page detail (path: instead of slug: to support nested slugs like legacy/about)
    path("<path:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
