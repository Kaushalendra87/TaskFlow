from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


class LogoutTests(APITestCase):
    def test_logout_blacklists_refresh_token(self):
        user = get_user_model().objects.create_user(
            username="logout-user",
            email="logout@example.com",
            password="secure-password",
        )
        refresh_token = str(RefreshToken.for_user(user))

        response = self.client.post(
            reverse("logout"),
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        refresh_response = self.client.post(
            reverse("token_refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, 401)
