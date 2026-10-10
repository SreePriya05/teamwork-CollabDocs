import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, models
from django.test.utils import isolate_apps
from django.urls import reverse
from rest_framework.test import APITestCase, APITransactionTestCase

from .models import Workspace, WorkspaceMember


def create_user(number):
    return get_user_model().objects.create_user(
        email=f"user{number}@example.com", password="test-password",
        first_name="Test", last_name="User", phone=f"900000{number:04d}",
    )


class WorkspaceAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = create_user(1)
        cls.editor = create_user(2)
        cls.viewer = create_user(3)
        cls.outsider = create_user(4)
        cls.workspace = Workspace.objects.create(name="Team", owner=cls.owner)
        for user, role in (
            (cls.owner, "admin"), (cls.editor, "editor"), (cls.viewer, "viewer")
        ):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=role)

    def setUp(self):
        self.client.force_authenticate(self.owner)
        self.detail_url = reverse("workspaces:workspace-detail", args=[self.workspace.pk])
        self.members_url = reverse("workspaces:workspace-members", args=[self.workspace.pk])
        self.summary_url = reverse("workspaces:workspace-summary", args=[self.workspace.pk])

    def test_creation_assigns_requester_as_owner_and_admin(self):
        response = self.client.post(reverse("workspaces:workspace-create"), {
            "name": "New team", "owner": str(self.outsider.pk)
        }, format="json")
        self.assertEqual(response.status_code, 201)
        workspace = Workspace.objects.get(pk=response.data["id"])
        self.assertEqual(workspace.owner, self.owner)
        self.assertTrue(workspace.is_active)
        self.assertEqual(response.data["member_count"], 1)
        member = workspace.members.get()
        self.assertEqual(member.user, self.owner)
        self.assertEqual(member.role, "admin")

    def test_creation_rolls_back_if_admin_membership_fails(self):
        before = Workspace.objects.count()
        with patch("workspaces.views.WorkspaceMember.objects.create", side_effect=IntegrityError("failure")):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("workspaces:workspace-create"), {"name": "Rollback"})
        self.assertEqual(Workspace.objects.count(), before)
        self.assertFalse(Workspace.objects.filter(name="Rollback").exists())

    def test_name_validation(self):
        for data in ({}, {"name": "   "}, {"name": "x" * 256}):
            with self.subTest(data=data):
                response = self.client.post(reverse("workspaces:workspace-create"), data)
                self.assertEqual(response.status_code, 400)

    def test_retrieve_member_count_for_all_roles(self):
        for user in (self.owner, self.editor, self.viewer):
            self.client.force_authenticate(user)
            response = self.client.get(self.detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["member_count"], 3)

    def test_add_member_and_list_safe_nested_user(self):
        response = self.client.post(self.members_url, {"user": str(self.outsider.pk), "role": "viewer"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["id"], str(self.outsider.pk))
        self.assertEqual(response.data["role"], "viewer")
        self.client.force_authenticate(self.outsider)
        response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 4)
        for member in response.data:
            self.assertEqual(set(member["user"]), {"id", "first_name", "last_name", "email"})

    def test_member_list_has_constant_query_count(self):
        with self.assertNumQueries(2):
            response = self.client.get(self.members_url)
        self.assertEqual(response.status_code, 200)
        for number in range(5, 10):
            WorkspaceMember.objects.create(workspace=self.workspace, user=create_user(number), role="viewer")
        with self.assertNumQueries(2):
            response = self.client.get(self.members_url)
        self.assertEqual(len(response.data), 8)

    def test_duplicate_member_conflict_leaves_transaction_usable(self):
        response = self.client.post(self.members_url, {"user": str(self.viewer.pk), "role": "editor"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.workspace.members.count(), 3)
        self.assertEqual(self.workspace.members.get(user=self.viewer).role, "viewer")
        response = self.client.post(self.members_url, {"user": str(self.outsider.pk), "role": "editor"})
        self.assertEqual(response.status_code, 201)

    def test_invalid_membership_input(self):
        for data in (
            {"user": str(self.outsider.pk), "role": "invalid"},
            {"user": str(uuid.uuid4()), "role": "viewer"},
            {"user": "not-a-uuid", "role": "viewer"},
            {"user": str(self.outsider.pk)}, {},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.members_url, data).status_code, 400)
        self.assertEqual(self.workspace.members.count(), 3)

    def test_non_admin_members_cannot_add_members(self):
        for user in (self.editor, self.viewer):
            self.client.force_authenticate(user)
            response = self.client.post(self.members_url, {"user": str(self.outsider.pk), "role": "viewer"})
            self.assertEqual(response.status_code, 403)

    def test_another_admin_can_add_members(self):
        membership = self.workspace.members.get(user=self.editor)
        membership.role = "admin"
        membership.save()
        self.client.force_authenticate(self.editor)
        response = self.client.post(self.members_url, {"user": str(self.outsider.pk), "role": "viewer"})
        self.assertEqual(response.status_code, 201)

    def test_outsider_cannot_access_workspace(self):
        self.client.force_authenticate(self.outsider)
        for url in (self.detail_url, self.members_url, self.summary_url):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(self.members_url, {"user": str(self.outsider.pk), "role": "admin"}).status_code, 404)

    def test_nonexistent_workspace(self):
        self.assertEqual(self.client.get(reverse("workspaces:workspace-detail", args=[uuid.uuid4()])).status_code, 404)

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(reverse("workspaces:workspace-create"), {"name": "Team"}).status_code, 403)
        for url in (self.detail_url, self.members_url, self.summary_url):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_summary_reports_missing_dependencies(self):
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["missing_models"], ["comments.Comment"])
        self.assertNotIn("total_comments", response.data)

    def test_unrequested_crud_methods_are_not_exposed(self):
        self.assertEqual(self.client.get(reverse("workspaces:workspace-create")).status_code, 405)
        self.assertEqual(self.client.patch(self.detail_url, {"name": "Changed"}).status_code, 405)
        self.assertEqual(self.client.delete(self.detail_url).status_code, 405)


class WorkspaceSummaryTests(APITransactionTestCase):
    @isolate_apps()
    def test_independent_counts_exclude_other_workspaces(self):
        # Temporary tables exist only in the test database, not teammate apps.
        class SummaryDocument(models.Model):
            workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)

            class Meta:
                app_label = "workspaces"

        class SummaryComment(models.Model):
            document = models.ForeignKey(SummaryDocument, on_delete=models.CASCADE)

            class Meta:
                app_label = "workspaces"

        with connection.schema_editor() as editor:
            editor.create_model(SummaryDocument)
            editor.create_model(SummaryComment)
        try:
            user = create_user(10)
            workspace = Workspace.objects.create(name="Summary", owner=user)
            other = Workspace.objects.create(name="Other", owner=user)
            WorkspaceMember.objects.create(workspace=workspace, user=user, role="admin")
            WorkspaceMember.objects.create(workspace=workspace, user=create_user(11), role="viewer")
            first = SummaryDocument.objects.create(workspace=workspace)
            second = SummaryDocument.objects.create(workspace=workspace)
            outside = SummaryDocument.objects.create(workspace=other)
            SummaryComment.objects.bulk_create([
                SummaryComment(document=first), SummaryComment(document=first),
                SummaryComment(document=second), SummaryComment(document=outside),
            ])
            self.client.force_authenticate(user)
            registry = {"documents.Document": SummaryDocument, "comments.Comment": SummaryComment}
            with patch("workspaces.views.apps.get_model", side_effect=registry.__getitem__):
                response = self.client.get(reverse("workspaces:workspace-summary", args=[workspace.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {"document_count": 2, "member_count": 2, "total_comments": 3})
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(SummaryComment)
                editor.delete_model(SummaryDocument)
