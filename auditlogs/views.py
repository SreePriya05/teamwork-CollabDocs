from django.db.models import Count, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor")
        params = self.request.query_params

        actor = params.get("actor_id") or params.get("actor")
        if actor:
            qs = qs.filter(actor_id=actor)

        model_name = params.get("model_name")
        if model_name:
            qs = qs.filter(model_name__icontains=model_name)

        start = params.get("start_date") or params.get("start")
        if start:
            qs = qs.filter(timestamp__gte=start)

        end = params.get("end_date") or params.get("end")
        if end:
            qs = qs.filter(timestamp__lte=end)

        return qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        counts = self.get_queryset().aggregate(
            total=Count("id"),
            created_count=Count("id", filter=Q(action=AuditLog.Action.CREATED)),
            updated_count=Count("id", filter=Q(action=AuditLog.Action.UPDATED)),
        )
        return Response(counts)
