from django.urls import path

from .views import DocumentViewSet

app_name = "documents"

urlpatterns = [
    path("", DocumentViewSet.as_view({"get": "list", "post": "create"}), name="document-list"),
    path("<uuid:pk>/", DocumentViewSet.as_view({"put": "update"}), name="document-detail"),
    path("<uuid:pk>/versions/", DocumentViewSet.as_view({"get": "versions"}), name="document-versions"),
    path("<uuid:pk>/stats/", DocumentViewSet.as_view({"get": "stats"}), name="document-stats"),
    path("<uuid:pk>/tags/", DocumentViewSet.as_view({"post": "tags"}), name="document-tags"),
]
