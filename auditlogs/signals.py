from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from documents.models import Document

from .models import AuditLog


@receiver(pre_save, sender=Document)
def capture_document_adding_state(sender, instance, **kwargs):
    instance._audit_action = (
        AuditLog.Action.CREATED if instance._state.adding else AuditLog.Action.UPDATED
    )


@receiver(post_save, sender=Document)
def log_document_change(sender, instance, **kwargs):
    action = getattr(instance, "_audit_action", AuditLog.Action.UPDATED)
    AuditLog.objects.create(
        actor=instance.created_by,
        action=action,
        model_name="Document",
        object_id=str(instance.pk),
    )
