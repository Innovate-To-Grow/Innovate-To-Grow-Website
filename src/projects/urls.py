from django.urls import path

from .views import CurrentProjectsAPIView, PastProjectsAPIView, ProjectDetailAPIView

app_name = "projects"

urlpatterns = [
    path("current/", CurrentProjectsAPIView.as_view(), name="projects-current"),
    path("past/", PastProjectsAPIView.as_view(), name="projects-past"),
    path("<uuid:pk>/", ProjectDetailAPIView.as_view(), name="project-detail"),
]
