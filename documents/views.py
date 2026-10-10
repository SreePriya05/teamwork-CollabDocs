from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from comments.models import Tag
from comments.serializers import TagSerializer

from .models import Document
from .serializers import DocumentSerializer, DocumentTagAttachSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Document.objects.select_related("workspace", "created_by").prefetch_related("tags")
        params = self.request.query_params

        document_status = params.get("status")
        if document_status:
            qs = qs.filter(status=document_status)

        workspace = params.get("workspace")
        if workspace:
            qs = qs.filter(workspace_id=workspace)

        search = params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

        tag = params.get("tag")
        if tag:
            qs = qs.filter(tags__name__icontains=tag).distinct()

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=True, methods=["post", "get"], url_path="tags")
    def tags(self, request, pk=None):
        document = get_object_or_404(
            Document.objects.select_related("workspace", "created_by"),
            pk=pk,
        )

        if request.method == "GET":
            tags = document.tags.annotate(document_count=Count("documents"))
            return Response(TagSerializer(tags, many=True).data)

        serializer = DocumentTagAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            names = serializer.validated_data.get("tags", [])
            tag_ids = serializer.validated_data.get("tag_ids", [])
            tags = [Tag.objects.get_or_create(name=name)[0] for name in names]
            if tag_ids:
                tags.extend(list(Tag.objects.filter(id__in=tag_ids)))
            if tags:
                document.tags.add(*tags)

        document = Document.objects.select_related("workspace", "created_by").prefetch_related("tags").get(pk=document.pk)
        return Response(DocumentSerializer(document).data, status=status.HTTP_200_OK)
