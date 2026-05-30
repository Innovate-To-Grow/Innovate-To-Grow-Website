from django.urls import path

from .views import (
    ModelListView,
    ModelSchemaView,
    OAuthAuthorizeView,
    OAuthTokenView,
    RecordCollectionView,
    RecordDetailView,
    WhoAmIView,
)

app_name = "cli_admin"

urlpatterns = [
    path("oauth/authorize/", OAuthAuthorizeView.as_view(), name="oauth-authorize"),
    path("oauth/token/", OAuthTokenView.as_view(), name="oauth-token"),
    path("whoami/", WhoAmIView.as_view(), name="whoami"),
    path("models/", ModelListView.as_view(), name="model-list"),
    path("models/<str:app_label>/<str:model_name>/schema/", ModelSchemaView.as_view(), name="model-schema"),
    path("records/<str:app_label>/<str:model_name>/", RecordCollectionView.as_view(), name="record-collection"),
    path("records/<str:app_label>/<str:model_name>/<str:pk>/", RecordDetailView.as_view(), name="record-detail"),
]
