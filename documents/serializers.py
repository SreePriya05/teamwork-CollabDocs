import uuid

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from comments.models import Tag
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
        user=user,
        workspace=workspace,
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
        fields = [
            "id",
            "title",
            "content",
            "workspace",
            "created_by",
            "status",
            "created_at",
            "updated_at",
            "version_count",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_version_count(self, obj):
        return obj.version_count

    def validate_workspace(self, workspace):
        if self.instance and workspace.pk != self.instance.workspace_id:
            raise serializers.ValidationError(
                "A document cannot be moved to another workspace."
            )
        require_document_editor(self.context["request"].user, workspace)
        return workspace


class DocumentVersionSerializer(serializers.ModelSerializer):
    saved_by = MemberUserSerializer(read_only=True)

    class Meta:
        model = DocumentVersion
        fields = ["id", "document", "content", "version_number", "saved_by", "saved_at"]
        read_only_fields = fields


class DocumentTagAttachSerializer(serializers.Serializer):
    """Accept existing tag ids or tag names, plus an optional id list."""

    tags = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=False,
    )
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        tag_ids = []
        names = []
        for raw in attrs["tags"]:
            text = raw.strip()
            if not text:
                raise serializers.ValidationError({"tags": "Tag names cannot be blank."})
            try:
                tag_ids.append(uuid.UUID(text))
            except ValueError:
                names.append(text.lower())

        tag_ids.extend(attrs.get("tag_ids", []))
        found = {tag.id: tag for tag in Tag.objects.filter(id__in=tag_ids)}
        missing = [str(tag_id) for tag_id in tag_ids if tag_id not in found]
        if missing:
            raise serializers.ValidationError(
                {"tags": f"Unknown tag ids: {', '.join(missing)}"}
            )

        resolved = [found[tag_id] for tag_id in tag_ids]
        for name in names:
            tag, _created = Tag.objects.get_or_create(name=name)
            resolved.append(tag)
        attrs["resolved_tags"] = resolved
        return attrs
