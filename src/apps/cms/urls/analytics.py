from django.urls import path

from apps.cms.views.analytics import PageViewCreateView

app_name = "analytics"

urlpatterns = [
    path("pageview/", PageViewCreateView.as_view(), name="pageview-create"),
]
