from io import StringIO
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from documents.models import Document
from workspaces.models import Workspace

from .models import AuditLog


class AuditLogTests(APITestCase):
    def setUp(self):
        self.actor = User.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="9876543210",
        )
        self.workspace = Workspace.objects.create(name="Research", owner=self.actor)

    def test_document_create_writes_created_audit_log(self):
        document = Document.objects.create(
            title="Notes",
            content="First draft",
            workspace=self.workspace,
            created_by=self.actor,
        )
        log = AuditLog.objects.get(object_id=str(document.id), action=AuditLog.Action.CREATED)
        self.assertEqual(log.model_name, "Document")
        self.assertEqual(log.actor_id, self.actor.id)

    def test_document_update_writes_updated_audit_log(self):
        document = Document.objects.create(
            title="Notes",
            content="First draft",
            workspace=self.workspace,
            created_by=self.actor,
        )
        document.title = "Updated notes"
        document.save()
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(document.id),
                action=AuditLog.Action.UPDATED,
            ).exists()
        )

    def test_audit_logs_are_read_only(self):
        response = self.client.post(
            reverse("auditlogs:audit-log-list"),
            {"action": "created", "model_name": "Document", "object_id": "abc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_filter_audit_logs_by_actor(self):
        document = Document.objects.create(
            title="Notes",
            content="First draft",
            workspace=self.workspace,
            created_by=self.actor,
        )
        response = self.client.get(
            reverse("auditlogs:audit-log-list"),
            {"actor_id": str(self.actor.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["object_id"], str(document.id))

    def test_audit_log_summary_aggregation(self):
        document = Document.objects.create(
            title="Notes",
            content="First draft",
            workspace=self.workspace,
            created_by=self.actor,
        )
        document.save()
        response = self.client.get(reverse("auditlogs:audit-log-summary"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["created_count"], 1)
        self.assertEqual(response.data["updated_count"], 1)


class RequestLoggingMiddlewareTests(SimpleTestCase):
    def test_logs_method_path_status_and_duration(self):
        with patch("sys.stdout", new_callable=StringIO) as captured:
            response = self.client.get("/api/health/")
        output = captured.getvalue()
        self.assertEqual(response.status_code, 200)
        self.assertIn("GET", output)
        self.assertIn("/api/health/", output)
        self.assertIn("200", output)
        self.assertIn("ms", output)
