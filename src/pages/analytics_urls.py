from django.urls import path

from pages.views.analytics import PageViewCreateView

app_name = "analytics"

urlpatterns = [
    path("pageview/", PageViewCreateView.as_view(), name="pageview-create"),
]
