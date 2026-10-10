from django.urls import path

from .views import WorkspaceViewSet

app_name = "workspaces"

urlpatterns = [
    path("", WorkspaceViewSet.as_view({"post": "create"}), name="workspace-create"),
    path(
        "<uuid:pk>/",
        WorkspaceViewSet.as_view({"get": "retrieve"}),
        name="workspace-detail",
    ),
    path(
        "<uuid:pk>/members/",
        WorkspaceViewSet.as_view({"get": "members", "post": "members"}),
        name="workspace-members",
    ),
    path(
        "<uuid:pk>/summary/",
        WorkspaceViewSet.as_view({"get": "summary"}),
        name="workspace-summary",
    ),
]
