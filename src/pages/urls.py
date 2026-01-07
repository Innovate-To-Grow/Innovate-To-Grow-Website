from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import (
    PageRetrieveAPIView,
    PageListAPIView,
    HomePageAPIView,
    SiteSettingsAPIView,
    UniformFormRetrieveAPIView,
    FormSubmissionCreateAPIView,
    FormSubmissionListAPIView,
    PastProjectsListAPIView,
    SharedProjectURLCreateAPIView,
    SharedProjectURLRetrieveAPIView,
)

app_name = "pages"

urlpatterns = [

    # pages list (for menu editor)
    path("", PageListAPIView.as_view(), name="page-list"),

    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),

    # site settings
    path("site-settings/", SiteSettingsAPIView.as_view(), name="site-settings"),

    # forms
    path("forms/<slug:slug>/", UniformFormRetrieveAPIView.as_view(), name="form-detail"),
    path("forms/<slug:slug>/submit/", FormSubmissionCreateAPIView.as_view(), name="form-submit"),
    path("forms/<slug:form_slug>/submissions/", FormSubmissionListAPIView.as_view(), name="form-submissions"),

    # past projects
    path("past-projects/", PastProjectsListAPIView.as_view(), name="past-projects-list"),
    path("past-projects/share/", csrf_exempt(SharedProjectURLCreateAPIView.as_view()), name="past-projects-share"),
    path("past-projects/shared/<uuid:uuid>/", SharedProjectURLRetrieveAPIView.as_view(), name="past-projects-shared"),

    # page detail
    path("<slug:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
