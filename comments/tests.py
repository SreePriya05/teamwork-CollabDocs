from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from documents.models import Document
from workspaces.models import Workspace

from .models import Comment, Tag


class CommentAndTagTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="9876543210",
        )
        self.workspace = Workspace.objects.create(name="Research", owner=self.author)
        self.document = Document.objects.create(
            title="Notes",
            content="First draft",
            workspace=self.workspace,
            created_by=self.author,
        )
        self.other_document = Document.objects.create(
            title="Other",
            content="Other draft",
            workspace=self.workspace,
            created_by=self.author,
        )

    def test_create_top_level_comment(self):
        response = self.client.post(
            reverse("comments:comment-list"),
            {
                "document": str(self.document.id),
                "author": str(self.author.id),
                "content": "Looks good",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["parent"])
        self.assertEqual(Comment.objects.count(), 1)

    def test_blank_comment_is_rejected(self):
        response = self.client.post(
            reverse("comments:comment-list"),
            {
                "document": str(self.document.id),
                "author": str(self.author.id),
                "content": "   ",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threaded_reply_and_listing(self):
        parent = Comment.objects.create(
            document=self.document,
            author=self.author,
            content="Top level",
        )
        response = self.client.post(
            reverse("comments:comment-list"),
            {
                "document": str(self.document.id),
                "author": str(self.author.id),
                "content": "A reply",
                "parent": str(parent.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent"], parent.id)

        listing = self.client.get(
            reverse("comments:comment-list"),
            {"document": str(self.document.id)},
        )
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(listing.data[0]["reply_count"], 1)
        self.assertEqual(listing.data[0]["replies"][0]["content"], "A reply")

    def test_reply_must_belong_to_same_document(self):
        parent = Comment.objects.create(
            document=self.document,
            author=self.author,
            content="Top level",
        )
        response = self.client.post(
            reverse("comments:comment-list"),
            {
                "document": str(self.other_document.id),
                "author": str(self.author.id),
                "content": "Cross-document reply",
                "parent": str(parent.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_create_tag(self):
        response = self.client.post(
            reverse("comments:tag-list"),
            {"name": " Python "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "python")

    def test_duplicate_tag_is_rejected(self):
        Tag.objects.create(name="python")
        response = self.client.post(
            reverse("comments:tag-list"),
            {"name": "Python"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attach_tags_to_document(self):
        existing = Tag.objects.create(name="api")
        response = self.client.post(
            reverse("documents:document-tags", args=[self.document.id]),
            {"tags": ["python", "django"], "tag_ids": [str(existing.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertCountEqual(response.data["tag_names"], ["api", "python", "django"])

        listed = self.client.get(reverse("documents:document-tags", args=[self.document.id]))
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 3)
