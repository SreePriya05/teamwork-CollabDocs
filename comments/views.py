from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Comment, Tag
from .serializers import CommentSerializer, TagSerializer


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        replies = Comment.objects.select_related("author", "document").order_by("created_at")
        qs = (
            Comment.objects.select_related("author", "document", "parent")
            .annotate(reply_count=Count("replies"))
            .prefetch_related(Prefetch("replies", queryset=replies))
        )

        document = self.request.query_params.get("document")
        if document:
            qs = qs.filter(document_id=document)

        author = self.request.query_params.get("author")
        if author:
            qs = qs.filter(author_id=author)

        if getattr(self, "action", None) == "list":
            qs = qs.filter(parent__isnull=True)

        return qs


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Tag.objects.annotate(document_count=Count("documents"))
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {"detail": "A tag with this name already exists."},
                status=status.HTTP_409_CONFLICT,
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
