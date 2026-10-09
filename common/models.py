import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Abstract base for application models that require UUID primary keys."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
