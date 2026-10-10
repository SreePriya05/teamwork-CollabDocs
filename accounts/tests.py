from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class UserEndpointTests(APITestCase):
    def test_register_user(self):
        url = reverse("accounts:user-list")
        payload = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone": "9876543210",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["full_name"], "Ada Lovelace")
        self.assertEqual(response.data["email"], "ada@example.com")
        self.assertTrue(User.objects.filter(email="ada@example.com").exists())

    def test_register_user_normalizes_email(self):
        response = self.client.post(
            reverse("accounts:user-list"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "  Ada@Example.COM ",
                "phone": "9876543210",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "ada@example.com")

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(
            reverse("accounts:user-list"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada@example.com",
                "phone": "12345",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_duplicate_email_is_rejected(self):
        User.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="9876543210",
        )
        response = self.client.post(
            reverse("accounts:user-list"),
            {
                "first_name": "Grace",
                "last_name": "Hopper",
                "email": "ada@example.com",
                "phone": "1234567890",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_user(self):
        user = User.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="9876543210",
        )
        url = reverse("accounts:user-detail", args=[user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(user.id))
        self.assertEqual(response.data["comment_count"], 0)
