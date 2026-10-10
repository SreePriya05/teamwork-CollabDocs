from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True, required=False)

    email = serializers.CharField(
        max_length=254,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                lookup="iexact",
                message="A user with this email already exists.",
            )
        ],
    )
    phone = serializers.CharField(
        max_length=15,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this phone already exists.",
            )
        ],
    )

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "is_active",
            "comment_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]

    def get_full_name(self, obj):
        return obj.full_name

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("First name cannot be blank.")
        return value

    def validate_last_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Last name cannot be blank.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if not value or "@" not in value:
            raise serializers.ValidationError("Enter a valid email address.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        if not (value.isdigit() and len(value) == 10):
            raise serializers.ValidationError(
                "Phone must be exactly 10 digits, with no spaces or special characters."
            )
        return value
