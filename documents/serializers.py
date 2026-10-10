from rest_framework import serializers

from comments.models import Tag

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    tag_names = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "content",
            "workspace",
            "created_by",
            "status",
            "tag_names",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_tag_names(self, obj):
        return list(obj.tags.values_list("name", flat=True))

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Document title cannot be blank.")
        return value


class DocumentTagAttachSerializer(serializers.Serializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=False,
        help_text="Tag names to attach to the document.",
    )
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )

    def validate_tags(self, value):
        names = []
        for name in value:
            normalized = name.strip().lower()
            if not normalized:
                raise serializers.ValidationError("Tag names cannot be blank.")
            names.append(normalized)
        return names

    def validate_tag_ids(self, value):
        existing = set(
            Tag.objects.filter(id__in=value).values_list("id", flat=True)
        )
        missing = [str(tag_id) for tag_id in value if tag_id not in existing]
        if missing:
            raise serializers.ValidationError(
                f"Unknown tag ids: {', '.join(missing)}"
            )
        return value
