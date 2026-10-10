from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Workspace, WorkspaceMember


class WorkspaceSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workspace
        fields = ["id", "name", "owner", "is_active", "created_at", "member_count"]
        read_only_fields = ["id", "owner", "created_at"]


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "first_name", "last_name", "email"]
        read_only_fields = fields


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ["id", "workspace", "user", "role", "joined_at"]
        read_only_fields = fields


class AddWorkspaceMemberSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), pk_field=serializers.UUIDField()
    )
    role = serializers.ChoiceField(choices=WorkspaceMember.Role.choices)
