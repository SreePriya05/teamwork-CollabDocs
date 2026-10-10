from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import CharField, Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from comments.serializers import TagSerializer
from workspaces.models import WorkspaceMember

from .models import Document, DocumentVersion
from .serializers import (
    DocumentSerializer,
    DocumentTagAttachSerializer,
    DocumentVersionSerializer,
    require_document_editor,
)


class IntegrationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "integration_unavailable"


class VersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A conflicting document version exists."
    default_code = "version_conflict"


def _is_constraint(exc, name, table):
    constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
    if constraint == name:
        return True
    return table in str(exc)


def tag_relationship():
    try:
        field = Document._meta.get_field("tags")
    except FieldDoesNotExist:
        raise IntegrationUnavailable("Document.tags ManyToManyField integration is unavailable.")
    if not field.many_to_many:
        raise IntegrationUnavailable("Document.tags must be a ManyToManyField.")
    return field


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "head", "options"]

    def get_queryset(self):
        workspace_ids = WorkspaceMember.objects.filter(
            user=self.request.user
        ).values_list("workspace_id", flat=True)
        queryset = (
            Document.objects.filter(workspace_id__in=workspace_ids)
            .select_related("workspace", "created_by")
            .annotate(version_count=Count("versions", distinct=True))
            .order_by("id")
        )
        if self.action != "list":
            return queryset
        params = self.request.query_params
        if "workspace" in params:
            workspace_id = serializers.UUIDField().run_validation(params["workspace"])
            queryset = queryset.filter(workspace_id=workspace_id)
        if "status" in params:
            status_filter = Q()
            for value in params.getlist("status"):
                value = serializers.ChoiceField(choices=Document.Status.choices).run_validation(value)
                status_filter |= Q(status=value)
            queryset = queryset.filter(status_filter)
        if "search" in params:
            queryset = queryset.filter(title__icontains=params["search"])
        if "tag" in params:
            field = tag_relationship()
            try:
                name_field = field.related_model._meta.get_field("name")
            except FieldDoesNotExist:
                raise IntegrationUnavailable("Tag name filtering requires a Tag.name field.")
            if not isinstance(name_field, CharField):
                raise IntegrationUnavailable("Tag name filtering requires a text Tag.name field.")
            queryset = queryset.filter(tags__name=params["tag"]).distinct()
        return queryset

    def save_version(self, document):
        version_number = document.versions.count() + 1
        DocumentVersion.objects.create(
            document=document,
            content=document.content,
            version_number=version_number,
            saved_by=self.request.user,
        )
        document.version_count = version_number

    def perform_create(self, serializer):
        with transaction.atomic():
            document = serializer.save(created_by=self.request.user)
            self.save_version(document)

    def update(self, request, *args, **kwargs):
        visible_document = self.get_object()
        try:
            with transaction.atomic():
                # Lock only the document row; aggregated querysets cannot be locked.
                document = get_object_or_404(
                    Document.objects.select_for_update(), pk=visible_document.pk
                )
                require_document_editor(request.user, document.workspace)
                serializer = self.get_serializer(document, data=request.data)
                serializer.is_valid(raise_exception=True)
                document = serializer.save()
                self.save_version(document)
                data = serializer.data
        except IntegrityError as exc:
            if _is_constraint(exc, "unique_document_version", "documents_documentversion"):
                raise VersionConflict() from exc
            raise
        return Response(data)

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        document = self.get_object()
        versions = document.versions.select_related("saved_by").order_by("version_number", "id")
        return Response(DocumentVersionSerializer(versions, many=True).data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        document = self.get_object()
        try:
            comment_model = apps.get_model("comments.Comment")
            relation = comment_model._meta.get_field("document")
        except (LookupError, FieldDoesNotExist):
            raise IntegrationUnavailable("Document stats require the Comment.document integration.")
        if not relation.many_to_one or relation.related_model is not Document:
            raise IntegrationUnavailable("Comment.document must reference Document.")
        version_stats = document.versions.aggregate(
            version_count=Count("pk", distinct=True),
            contributor_count=Count("saved_by", distinct=True),
        )
        comment_stats = comment_model.objects.filter(document=document).aggregate(
            comment_count=Count("pk", distinct=True)
        )
        return Response({**version_stats, **comment_stats})

    @action(detail=True, methods=["get", "post"])
    def tags(self, request, pk=None):
        document = self.get_object()
        tag_relationship()
        if request.method == "GET":
            tags = document.tags.annotate(document_count=Count("documents"))
            return Response(TagSerializer(tags, many=True).data)

        require_document_editor(request.user, document.workspace)
        serializer = DocumentTagAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            Document.objects.select_for_update().get(pk=document.pk)
            document.tags.add(*serializer.validated_data["resolved_tags"])
        rows = list(document.tags.values_list("pk", "name"))
        return Response(
            {
                "tags": [tag_id for tag_id, _name in rows],
                "tag_names": [name for _tag_id, name in rows],
            }
        )
