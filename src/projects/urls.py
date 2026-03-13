from django.urls import path

from .views import AllPastProjectsAPIView, CurrentProjectsAPIView, PastProjectsAPIView, ProjectDetailAPIView

app_name = "projects"

urlpatterns = [
    path("current/", CurrentProjectsAPIView.as_view(), name="projects-current"),
    path("past/", PastProjectsAPIView.as_view(), name="projects-past"),
    path("past-all/", AllPastProjectsAPIView.as_view(), name="projects-past-all"),
    path("<uuid:pk>/", ProjectDetailAPIView.as_view(), name="project-detail"),
]
