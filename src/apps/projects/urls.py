from django.urls import path
from django.views.generic import RedirectView

from .views import (
    AllPastProjectsAPIView,
    PastProjectAISearchAPIView,
    PastProjectsAPIView,
    ProjectDetailAPIView,
)

app_name = "projects"

urlpatterns = [
    path("current/", RedirectView.as_view(url="/event/projects/", permanent=True), name="projects-current-redirect"),
    path("past/", PastProjectsAPIView.as_view(), name="projects-past"),
    path("past-all/", AllPastProjectsAPIView.as_view(), name="projects-past-all"),
    path("past-ai-search/", PastProjectAISearchAPIView.as_view(), name="projects-past-ai-search"),
    path("<uuid:pk>/", ProjectDetailAPIView.as_view(), name="project-detail"),
]
