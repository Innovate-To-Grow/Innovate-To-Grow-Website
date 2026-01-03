from django.urls import path

from .views import (
    FormSubmissionCreateAPIView,
    FormSubmissionListAPIView,
    HomePageAPIView,
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
    # forms
    path("forms/<slug:slug>/", UniformFormRetrieveAPIView.as_view(), name="form-detail"),
    path("forms/<slug:slug>/submit/", FormSubmissionCreateAPIView.as_view(), name="form-submit"),
    path("forms/<slug:form_slug>/submissions/", FormSubmissionListAPIView.as_view(), name="form-submissions"),
    # page detail
    path("<slug:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
