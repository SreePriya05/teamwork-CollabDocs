"""Root URL configuration for the CollabDocs API."""
from django.contrib import admin
from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthCheckView.as_view(), name="health-check"),
    path("api/accounts/", include("accounts.urls")),
    path("api/workspaces/", include("workspaces.urls")),
    path("api/documents/", include("documents.urls")),
    path("api/comments/", include("comments.urls")),
    path("api/auditlogs/", include("auditlogs.urls")),
]
