from django.urls import path

from .views import (
    AllPastProjectsAPIView,
    CurrentProjectsAPIView,
    PastProjectsAPIView,
    PastProjectShareCreateAPIView,
    PastProjectShareDetailAPIView,
    ProjectDetailAPIView,
    ProjectImportAPIView,
    ProjectImportTemplateAPIView,
)

app_name = "projects"

urlpatterns = [
    path("current/", CurrentProjectsAPIView.as_view(), name="projects-current"),
    path("past/", PastProjectsAPIView.as_view(), name="projects-past"),
    path("past-all/", AllPastProjectsAPIView.as_view(), name="projects-past-all"),
    path("past-shares/", PastProjectShareCreateAPIView.as_view(), name="projects-past-share-create"),
    path("past-shares/<uuid:pk>/", PastProjectShareDetailAPIView.as_view(), name="projects-past-share-detail"),
    path("import/", ProjectImportAPIView.as_view(), name="projects-import"),
    path("import/template/", ProjectImportTemplateAPIView.as_view(), name="projects-import-template"),
    path("<uuid:pk>/", ProjectDetailAPIView.as_view(), name="project-detail"),
]
