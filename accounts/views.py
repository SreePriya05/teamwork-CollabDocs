from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import User
from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return User.objects.annotate(comment_count=Count("comments"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {"detail": "A user with this email or phone already exists."},
                status=status.HTTP_409_CONFLICT,
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
