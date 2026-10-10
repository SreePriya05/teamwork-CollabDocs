from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "action",
            "model_name",
            "object_id",
            "timestamp",
        ]
        read_only_fields = fields
