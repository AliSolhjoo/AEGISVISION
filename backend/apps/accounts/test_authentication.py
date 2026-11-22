from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="auth-user@example.com",
            password="Secure-Test-Password-2026!",
            first_name="Test",
            last_name="User",
        )
        self.token_url = reverse("auth:token-obtain")
        self.refresh_url = reverse("auth:token-refresh")
        self.register_url = reverse("auth:register")

    def login(self, email=None, password=None):
        response = self.client.post(
            self.token_url,
            {
                "email": email or self.user.email,
                "password": password or "Secure-Test-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def authenticate(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_registration_creates_user_and_hashes_password(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "NEW-USER@example.com",
                "first_name": "New",
                "last_name": "User",
                "password": "New-Strong-Password-2026!",
                "password_confirm": "New-Strong-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = User.objects.get(email="new-user@example.com")
        self.assertTrue(created.check_password("New-Strong-Password-2026!"))
        self.assertNotEqual(created.password, "New-Strong-Password-2026!")

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "AUTH-USER@example.com",
                "password": "Another-Strong-Password-2026!",
                "password_confirm": "Another-Strong-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_rejects_password_mismatch(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "mismatch@example.com",
                "password": "Strong-Password-2026!",
                "password_confirm": "Different-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "weak@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_access_refresh_and_profile(self):
        response = self.login()
        self.assertIn("access", response)
        self.assertIn("refresh", response)
        self.assertEqual(response["user"]["email"], self.user.email)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": "Secure-Test-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("auth:me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        tokens = self.login()
        self.authenticate(tokens["access"])
        response = self.client.get(reverse("auth:me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_refresh_rotates_token_and_rejects_old_refresh(self):
        tokens = self.login()
        response = self.client.post(
            self.refresh_url,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("access", response.data)
        self.assertNotEqual(response.data["refresh"], tokens["refresh"])

        replay = self.client.post(
            self.refresh_url,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        tokens = self.login()
        self.authenticate(tokens["access"])
        response = self.client.post(
            reverse("auth:logout"),
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        replay = self.client.post(
            self.refresh_url,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(BlacklistedToken.objects.exists())

    def test_logout_rejects_another_users_refresh_token(self):
        other = User.objects.create_user(
            email="another-user@example.com",
            password="Another-Secure-Password-2026!",
        )
        own_tokens = self.login()
        other_response = self.client.post(
            self.token_url,
            {"email": other.email, "password": "Another-Secure-Password-2026!"},
            format="json",
        )
        self.assertEqual(other_response.status_code, status.HTTP_200_OK)
        self.authenticate(own_tokens["access"])
        response = self.client.post(
            reverse("auth:logout"),
            {"refresh": other_response.data["refresh"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_password_revokes_refresh_tokens(self):
        tokens = self.login()
        self.authenticate(tokens["access"])
        response = self.client.post(
            reverse("auth:change-password"),
            {
                "current_password": "Secure-Test-Password-2026!",
                "new_password": "Brand-New-Strong-Password-2026!",
                "new_password_confirm": "Brand-New-Strong-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-Strong-Password-2026!"))
        refresh_replay = self.client.post(
            self.refresh_url,
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(refresh_replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_request_sends_email_for_existing_user(self):
        response = self.client.post(
            reverse("auth:password-reset"),
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password", mail.outbox[0].body)

    def test_password_reset_request_does_not_disclose_unknown_email(self):
        response = self.client.post(
            reverse("auth:password-reset"),
            {"email": "unknown@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("If an active account exists", response.data["message"])

    def test_password_reset_confirm_changes_password_and_token_is_single_use(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": "Reset-Strong-Password-2026!",
            "new_password_confirm": "Reset-Strong-Password-2026!",
        }
        response = self.client.post(
            reverse("auth:password-reset-confirm"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reset-Strong-Password-2026!"))

        replay = self.client.post(
            reverse("auth:password-reset-confirm"),
            payload,
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_rejects_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            reverse("auth:password-reset-confirm"),
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "Reset-Strong-Password-2026!",
                "new_password_confirm": "Reset-Strong-Password-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
