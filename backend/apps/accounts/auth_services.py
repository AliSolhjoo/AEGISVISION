from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from urllib.parse import urlencode

from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)


User = get_user_model()


def revoke_user_refresh_tokens(user):
    """Blacklist every outstanding refresh token issued to this user."""
    outstanding_tokens = OutstandingToken.objects.filter(user=user)

    for outstanding_token in outstanding_tokens.iterator():
        BlacklistedToken.objects.get_or_create(token=outstanding_token)


def send_password_reset_email(user):
    """Send a single-use password-reset link without exposing account state."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    frontend_url = getattr(
        settings,
        "FRONTEND_URL",
        "http://localhost:5173",
    ).rstrip("/")
    query = urlencode({"uid": uid, "token": token})
    reset_url = f"{frontend_url}/reset-password?{query}"

    message = (
        f"Hello {user.first_name or 'there'},\n\n"
        "We received a request to reset your AEGISVISION password.\n"
        "Use the following link to choose a new password:\n\n"
        f"{reset_url}\n\n"
        "This link is valid for a limited time and can only be used once.\n"
        "If you did not request this change, you can ignore this email.\n"
    )

    send_mail(
        subject="Reset your AEGISVISION password",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
