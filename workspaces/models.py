from django.db import models

from common.models import UUIDPrimaryKeyModel


class Workspace(UUIDPrimaryKeyModel):
    """Minimal workspace model required by documents (owned in full by Member 1)."""

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="owned_workspaces",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
