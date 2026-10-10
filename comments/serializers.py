from rest_framework import serializers

from .models import Comment, Tag


class CommentSerializer(serializers.ModelSerializer):
    replies = serializers.SerializerMethodField()
    reply_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Comment
        fields = [
            "id",
            "document",
            "author",
            "content",
            "parent",
            "reply_count",
            "replies",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_replies(self, obj):
        replies = obj.replies.all()
        return CommentSerializer(replies, many=True).data

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Comment content cannot be blank.")
        return value

    def validate(self, attrs):
        document = attrs.get("document") or getattr(self.instance, "document", None)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))

        if parent is not None:
            if document is not None and parent.document_id != document.id:
                raise serializers.ValidationError(
                    {"parent": "A reply's parent must belong to the same document."}
                )
            if self.instance is not None and parent.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"parent": "A comment cannot be a reply to itself."}
                )
        return attrs


class TagSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ["id", "name", "documents", "document_count", "created_at"]
        read_only_fields = ["id", "documents", "created_at"]

    def validate_name(self, value):
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Tag name cannot be blank.")

        qs = Tag.objects.filter(name=normalized)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A tag with this name already exists.")
        return normalized
