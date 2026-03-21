from django.urls import path

from analytics.views import PageViewCreateView

app_name = "analytics"

urlpatterns = [
    path("pageview/", PageViewCreateView.as_view(), name="pageview-create"),
]
