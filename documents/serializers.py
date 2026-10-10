from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from workspaces.models import Workspace, WorkspaceMember
from workspaces.serializers import MemberUserSerializer
from .models import Document, DocumentVersion


class StrictCharField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


def require_document_editor(user, workspace):
    if not WorkspaceMember.objects.filter(
        user=user, workspace=workspace,
        role__in=[WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.EDITOR],
    ).exists():
        raise PermissionDenied("Only workspace admins and editors can modify documents.")


class DocumentSerializer(serializers.ModelSerializer):
    title = StrictCharField(max_length=255)
    content = StrictCharField(trim_whitespace=False)
    workspace = serializers.PrimaryKeyRelatedField(
        queryset=Workspace.objects.all(), pk_field=serializers.UUIDField()
    )
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "title", "content", "workspace", "created_by", "status",
                  "updated_at", "version_count"]
        read_only_fields = ["id", "created_by", "updated_at"]

    def get_version_count(self, obj):
        return obj.version_count

    def validate_workspace(self, workspace):
        if self.instance and workspace.pk != self.instance.workspace_id:
            raise serializers.ValidationError("A document cannot be moved to another workspace.")
        require_document_editor(self.context["request"].user, workspace)
        return workspace


class DocumentVersionSerializer(serializers.ModelSerializer):
    saved_by = MemberUserSerializer(read_only=True)

    class Meta:
        model = DocumentVersion
        fields = ["id", "document", "content", "version_number", "saved_by", "saved_at"]
        read_only_fields = fields


class TagAssignmentSerializer(serializers.Serializer):
    def __init__(self, *args, tag_model, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"] = serializers.PrimaryKeyRelatedField(
            queryset=tag_model.objects.all(), many=True, allow_empty=False
        )
