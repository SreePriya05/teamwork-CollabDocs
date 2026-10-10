from django.db import models

from common.models import UUIDPrimaryKeyModel


class Comment(UUIDPrimaryKeyModel):
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    content = models.TextField()
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment {self.id}"


class Tag(UUIDPrimaryKeyModel):
    name = models.CharField(max_length=100, unique=True)
    documents = models.ManyToManyField(
        "documents.Document",
        related_name="tags",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
