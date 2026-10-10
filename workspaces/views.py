from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Workspace, WorkspaceMember
from .serializers import (
    AddWorkspaceMemberSerializer,
    WorkspaceMemberSerializer,
    WorkspaceSerializer,
)


class DuplicateMembership(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This user is already a workspace member."
    default_code = "duplicate_membership"


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        workspace_ids = WorkspaceMember.objects.filter(
            user=self.request.user
        ).values_list("workspace_id", flat=True)
        return (
            Workspace.objects.filter(id__in=workspace_ids)
            .select_related("owner")
            .annotate(member_count=Count("members", distinct=True))
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            workspace = serializer.save(owner=self.request.user)
            WorkspaceMember.objects.create(
                workspace=workspace,
                user=self.request.user,
                role=WorkspaceMember.Role.ADMIN,
            )
        workspace.member_count = 1

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        workspace = self.get_object()
        if request.method == "GET":
            members = workspace.members.select_related("user", "workspace").order_by(
                "joined_at", "id"
            )
            return Response(WorkspaceMemberSerializer(members, many=True).data)

        if not workspace.members.filter(
            user=request.user, role=WorkspaceMember.Role.ADMIN
        ).exists():
            raise PermissionDenied("Only workspace admins can add members.")

        serializer = AddWorkspaceMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                member = WorkspaceMember.objects.create(
                    workspace=workspace, **serializer.validated_data
                )
        except IntegrityError as exc:
            # Catch outside the atomic block so the failed transaction is rolled back.
            constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
            if constraint == "unique_workspace_member":
                raise DuplicateMembership() from exc
            raise
        return Response(
            WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        workspace = self.get_object()
        missing = []
        models = {}
        for label in ("documents.Document", "comments.Comment"):
            try:
                models[label] = apps.get_model(label)
            except LookupError:
                missing.append(label)
        if missing:
            return Response(
                {"detail": "Workspace summary dependencies are unavailable.",
                 "missing_models": missing},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        document_model = models["documents.Document"]
        comment_model = models["comments.Comment"]
        try:
            workspace_field = document_model._meta.get_field("workspace")
            document_field = comment_model._meta.get_field("document")
            compatible = (
                workspace_field.many_to_one
                and workspace_field.related_model is Workspace
                and document_field.many_to_one
                and document_field.related_model is document_model
            )
        except FieldDoesNotExist:
            compatible = False
        if not compatible:
            return Response(
                {"detail": "Workspace summary requires Document.workspace and Comment.document foreign keys."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # Independent aggregates prevent multiplication across unrelated joins.
        documents = document_model.objects.filter(workspace=workspace).aggregate(
            document_count=Count("pk", distinct=True)
        )
        comments = comment_model.objects.filter(document__workspace=workspace).aggregate(
            total_comments=Count("pk", distinct=True)
        )
        return Response(
            {**documents, "member_count": workspace.member_count, **comments}
        )
