import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, models
from django.test import skipUnlessDBFeature
from django.test.utils import isolate_apps
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from workspaces.models import Workspace, WorkspaceMember
from .models import Document, DocumentVersion


def create_user(number):
    return get_user_model().objects.create_user(
        email=f"doc{number}@example.com", first_name="Test", last_name="User",
        phone=f"800000{number:04d}", password="test-password",
    )


class DocumentAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin, cls.editor, cls.viewer, cls.outsider = [create_user(n) for n in range(1, 5)]
        cls.workspace = Workspace.objects.create(name="Documents", owner=cls.admin)
        cls.other_workspace = Workspace.objects.create(name="Other", owner=cls.outsider)
        for user, role in ((cls.admin, "admin"), (cls.editor, "editor"), (cls.viewer, "viewer")):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=role)
        WorkspaceMember.objects.create(workspace=cls.other_workspace, user=cls.outsider, role="admin")
        cls.document = Document.objects.create(
            title="Alpha Guide", content="First", workspace=cls.workspace,
            created_by=cls.admin, status="draft",
        )
        DocumentVersion.objects.create(document=cls.document, content="First", version_number=1, saved_by=cls.admin)
        cls.other = Document.objects.create(
            title="Hidden", content="Other", workspace=cls.other_workspace,
            created_by=cls.outsider, status="published",
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)
        self.list_url = reverse("documents:document-list")
        self.detail_url = reverse("documents:document-detail", args=[self.document.pk])
        self.versions_url = reverse("documents:document-versions", args=[self.document.pk])
        self.stats_url = reverse("documents:document-stats", args=[self.document.pk])
        self.tags_url = reverse("documents:document-tags", args=[self.document.pk])

    def payload(self, **changes):
        return {"title": "A guide", "content": "New content", "status": "draft",
                "workspace": str(self.workspace.pk), **changes}

    def test_creation_and_first_version_for_admin_and_editor(self):
        for user in (self.admin, self.editor):
            self.client.force_authenticate(user)
            response = self.client.post(self.list_url, self.payload(created_by=str(self.outsider.pk)), format="json")
            self.assertEqual(response.status_code, 201)
            document = Document.objects.get(pk=response.data["id"])
            self.assertEqual(document.created_by, user)
            self.assertEqual(response.data["version_count"], 1)
            version = document.versions.get()
            self.assertEqual(version.version_number, 1)
            self.assertEqual(version.saved_by, user)
            self.assertEqual(version.content, document.content)

    def test_updates_have_sequential_versions_and_preserve_creator(self):
        self.client.force_authenticate(self.editor)
        for number in range(2, 5):
            response = self.client.put(self.detail_url, self.payload(content=f"Version {number}", created_by=str(self.editor.pk)), format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["version_count"], number)
        self.document.refresh_from_db()
        self.assertEqual(self.document.created_by, self.admin)
        self.assertEqual(self.document.content, "Version 4")
        self.assertEqual(list(self.document.versions.order_by("version_number").values_list("version_number", flat=True)), [1, 2, 3, 4])
        self.assertEqual(self.document.versions.get(version_number=4).saved_by, self.editor)

    def test_creation_rolls_back_when_version_fails(self):
        before = Document.objects.count()
        with patch("documents.views.DocumentVersion.objects.create", side_effect=IntegrityError("version failure")):
            with self.assertRaises(IntegrityError):
                self.client.post(self.list_url, self.payload(), format="json")
        self.assertEqual(Document.objects.count(), before)

    def test_update_rolls_back_when_version_fails(self):
        original_updated_at = self.document.updated_at
        with patch("documents.views.DocumentVersion.objects.create", side_effect=IntegrityError("version failure")):
            with self.assertRaises(IntegrityError):
                self.client.put(self.detail_url, self.payload(content="Rollback"), format="json")
        self.document.refresh_from_db()
        self.assertEqual(self.document.content, "First")
        self.assertEqual(self.document.title, "Alpha Guide")
        self.assertEqual(self.document.updated_at, original_updated_at)
        self.assertEqual(self.document.versions.count(), 1)

    def test_version_conflict_returns_409_and_rolls_back(self):
        DocumentVersion.objects.create(document=self.document, content="Gap", version_number=3, saved_by=self.admin)
        response = self.client.put(self.detail_url, self.payload(content="Conflict"), format="json")
        self.assertEqual(response.status_code, 409)
        self.document.refresh_from_db()
        self.assertEqual(self.document.content, "First")
        self.assertEqual(self.document.versions.count(), 2)

    def test_viewers_can_read_but_not_write(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
        self.assertEqual(self.client.get(self.versions_url).status_code, 200)
        self.assertEqual(self.client.post(self.list_url, self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.put(self.detail_url, self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.post(self.tags_url, {"tags": []}, format="json").status_code, 403)

    def test_outsider_cannot_access_document(self):
        self.client.force_authenticate(self.outsider)
        response = self.client.get(self.list_url)
        self.assertEqual([item["id"] for item in response.data], [str(self.other.pk)])
        for url in (self.versions_url, self.stats_url):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(self.detail_url, self.payload(), format="json").status_code, 404)
        self.assertEqual(self.client.post(self.tags_url, {"tags": []}, format="json").status_code, 404)
        self.assertEqual(self.client.post(self.list_url, self.payload(), format="json").status_code, 403)

    def test_anonymous_access_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(self.list_url, self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.get(self.versions_url).status_code, 403)

    def test_invalid_document_input(self):
        for changes in (
            {"title": ""}, {"title": "   "}, {"title": "x" * 256}, {"title": 123},
            {"content": {}}, {"content": 123}, {"content": None}, {"status": "invalid"},
            {"workspace": "bad"}, {"workspace": str(uuid.uuid4())},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(self.list_url, self.payload(**changes), format="json").status_code, 400)
        self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 400)

    def test_cannot_move_document_to_another_workspace(self):
        WorkspaceMember.objects.create(workspace=self.other_workspace, user=self.admin, role="admin")
        response = self.client.put(self.detail_url, self.payload(workspace=str(self.other_workspace.pk)), format="json")
        self.assertEqual(response.status_code, 400)
        self.document.refresh_from_db()
        self.assertEqual(self.document.workspace, self.workspace)

    def test_filters_and_case_insensitive_search(self):
        published = Document.objects.create(title="Beta GUIDE", content="Text", workspace=self.workspace, created_by=self.admin, status="published")
        archived = Document.objects.create(title="Old", content="Text", workspace=self.workspace, created_by=self.admin, status="archived")
        for params, expected in (
            ({"workspace": str(self.workspace.pk)}, {self.document.pk, published.pk, archived.pk}),
            ({"workspace": str(self.other_workspace.pk)}, set()),
            ({"status": "published"}, {published.pk}),
            ({"search": "gUiDe"}, {self.document.pk, published.pk}),
            ({"status": "published", "search": "guide"}, {published.pk}),
        ):
            response = self.client.get(self.list_url, params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual({item["id"] for item in response.data}, {str(pk) for pk in expected})
        response = self.client.get(self.list_url + "?status=draft&status=published")
        self.assertEqual({item["id"] for item in response.data}, {str(self.document.pk), str(published.pk)})
        for params in ({"workspace": "bad"}, {"status": "invalid"}):
            self.assertEqual(self.client.get(self.list_url, params).status_code, 400)

    def test_list_has_no_n_plus_one_queries(self):
        with self.assertNumQueries(1):
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        for number in range(3):
            Document.objects.create(title=f"Document {number}", content="Text", workspace=self.workspace, created_by=self.editor, status="draft")
        with self.assertNumQueries(1):
            response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 4)

    def test_versions_are_ordered_and_user_fields_are_safe(self):
        for number in (3, 2):
            DocumentVersion.objects.create(document=self.document, content=str(number), version_number=number, saved_by=self.editor)
        with self.assertNumQueries(2):
            response = self.client.get(self.versions_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([v["version_number"] for v in response.data], [1, 2, 3])
        self.assertEqual(set(response.data[0]["saved_by"]), {"id", "first_name", "last_name", "email"})

    def test_comments_and_tags_are_integrated(self):
        response = self.client.get(self.stats_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"version_count": 1, "contributor_count": 1, "comment_count": 0},
        )
        self.assertEqual(self.client.post(self.tags_url, {"tags": []}, format="json").status_code, 400)
        response = self.client.get(self.list_url, {"tag": "important"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_only_requested_methods_are_exposed(self):
        self.assertEqual(self.client.get(self.detail_url).status_code, 405)
        self.assertEqual(self.client.patch(self.detail_url, {}).status_code, 405)
        self.assertEqual(self.client.delete(self.detail_url).status_code, 405)


class DocumentIntegrationTests(APITransactionTestCase):
    def setUp(self):
        self.admin = create_user(20)
        self.editor = create_user(21)
        self.workspace = Workspace.objects.create(name="Integration", owner=self.admin)
        for user in (self.admin, self.editor):
            WorkspaceMember.objects.create(workspace=self.workspace, user=user, role="editor")
        self.document = Document.objects.create(title="Test", content="Text", workspace=self.workspace, created_by=self.admin, status="draft")
        DocumentVersion.objects.create(document=self.document, content="Text", version_number=1, saved_by=self.admin)
        self.client.force_authenticate(self.admin)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_updates_get_distinct_sequential_versions(self):
        barrier = Barrier(2)
        url = reverse("documents:document-detail", args=[self.document.pk])

        def update(number):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.editor)
                barrier.wait(timeout=10)
                response = client.put(url, {"title": "Test", "content": f"Concurrent {number}",
                    "workspace": str(self.workspace.pk), "status": "draft"}, format="json")
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, [1, 2]))
        self.assertEqual(results, [200, 200])
        versions = self.document.versions.order_by("version_number")
        self.assertEqual(list(versions.values_list("version_number", flat=True)), [1, 2, 3])
        self.assertEqual(set(versions.exclude(version_number=1).values_list("content", flat=True)), {"Concurrent 1", "Concurrent 2"})

    @isolate_apps()
    def test_stats_count_distinct_contributors_and_scoped_comments(self):
        # Temporary integration fixtures exist only in the test database.
        class IntegrationComment(models.Model):
            document = models.ForeignKey(Document, on_delete=models.CASCADE)

            class Meta:
                app_label = "documents"

        with connection.schema_editor() as editor:
            editor.create_model(IntegrationComment)
        try:
            other = Document.objects.create(title="Other", content="Text", workspace=self.workspace, status="draft")
            IntegrationComment.objects.bulk_create([
                IntegrationComment(document=self.document), IntegrationComment(document=self.document),
                IntegrationComment(document=other),
            ])
            for number, user in ((2, self.editor), (3, self.editor), (4, None)):
                DocumentVersion.objects.create(document=self.document, content="Text", version_number=number, saved_by=user)
            with patch("documents.views.apps.get_model", return_value=IntegrationComment):
                response = self.client.get(reverse("documents:document-stats", args=[self.document.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {"version_count": 4, "contributor_count": 2, "comment_count": 2})
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(IntegrationComment)

    def test_tag_assignment_and_filter_with_integrated_relationship(self):
        from comments.models import Tag

        tags = [Tag.objects.create(name=name) for name in ("important", "review")]
        url = reverse("documents:document-tags", args=[self.document.pk])
        for ids in ([str(tag.pk) for tag in tags], [str(tags[0].pk)]):
            response = self.client.post(url, {"tags": ids}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data["tags"]), {tag.pk for tag in tags})
        self.assertEqual(self.document.tags.count(), 2)
        self.assertEqual(self.document.versions.count(), 1)
        for data in ({"tags": []}, {"tags": [str(uuid.uuid4())]}, {"tags": "invalid"}):
            self.assertEqual(self.client.post(url, data, format="json").status_code, 400)
        named = self.client.post(url, {"tags": ["release"]}, format="json")
        self.assertEqual(named.status_code, 200)
        self.assertIn("release", named.data["tag_names"])
        response = self.client.get(reverse("documents:document-list"), {"tag": "important"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [str(self.document.pk)])
