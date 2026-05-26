from django.urls import path

from .views import (
    MiniAppCodeView,
    MiniAppDataDetailView,
    MiniAppDataListCreateView,
    MiniAppResolveView,
    MiniAppSchemaView,
)

urlpatterns = [
    path("resolve/", MiniAppResolveView.as_view(), name="miniapp-resolve"),
    path("<slug:app_slug>/code/", MiniAppCodeView.as_view(), name="miniapp-code"),
    path("<slug:app_slug>/schema/", MiniAppSchemaView.as_view(), name="miniapp-schema"),
    path("<slug:app_slug>/data/", MiniAppDataListCreateView.as_view(), name="miniapp-data-list"),
    path("<slug:app_slug>/data/<uuid:record_id>/", MiniAppDataDetailView.as_view(), name="miniapp-data-detail"),
]
