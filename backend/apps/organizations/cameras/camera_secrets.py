"""Authenticated encryption helpers for RTSP camera credentials.

The encryption key is derived from Django SECRET_KEY and a versioned context.
Credential ciphertext is never exposed by API serializers or logs.
"""
from __future__ import annotations

import base64
import hashlib
import json

from django.conf import settings


_CONTEXT = b"AEGISVISION_CAMERA_CREDENTIALS_V1"


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dependency installation path
        raise RuntimeError(
            "Camera credential encryption requires the 'cryptography' package. "
            "Install it with: python -m pip install cryptography"
        ) from exc

    secret = str(getattr(settings, "SECRET_KEY", "") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("Django SECRET_KEY is missing or too short for camera credential encryption.")
    digest = hashlib.sha256(_CONTEXT + secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_camera_credentials(username: str, password: str) -> str:
    payload = json.dumps(
        {"username": str(username), "password": str(password)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_camera_credentials(ciphertext: str) -> dict[str, str]:
    if not ciphertext:
        return {"username": "", "password": ""}
    try:
        payload = _fernet().decrypt(ciphertext.encode("ascii"))
        value = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Stored camera credentials could not be decrypted. Verify that the original Django SECRET_KEY is unchanged."
        ) from exc
    username = value.get("username", "") if isinstance(value, dict) else ""
    password = value.get("password", "") if isinstance(value, dict) else ""
    return {"username": str(username), "password": str(password)}
