from urllib.parse import quote, urlsplit, urlunsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator

from .camera_secrets import decrypt_camera_credentials, encrypt_camera_credentials


class Camera(models.Model):
    """A camera/source registered inside one AEGISVISION organization.

    RTSP credentials are accepted through dedicated write-only serializer fields
    and stored using authenticated encryption; they are never embedded in logs
    or returned by API serializers.
    """

    class SourceType(models.TextChoices):
        RTSP = "rtsp", "RTSP"
        RTSPS = "rtsps", "RTSPS"
        BROWSER = "browser", "Browser camera"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        ERROR = "error", "Error"
        DISABLED = "disabled", "Disabled"

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="cameras",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_cameras",
    )
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=64)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=180, blank=True)
    source_type = models.CharField(
        max_length=12,
        choices=SourceType.choices,
        default=SourceType.RTSP,
    )
    # Write-only in API. Usernames/passwords are stored separately as ciphertext.
    stream_url = models.CharField(max_length=2048, blank=True)
    # Username/password are encrypted together; ciphertext is never serialized.
    credentials_encrypted = models.TextField(blank=True, editable=False)
    target_fps = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Maximum AI inference frames per second for live processing.",
    )
    confidence_threshold = models.FloatField(
        default=0.55,
        validators=[MinValueValidator(0.05), MaxValueValidator(0.99)],
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "organizations"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_org_camera_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="camera_org_status_idx",
            ),
            models.Index(
                fields=["organization", "created_at"],
                name="camera_org_created_idx",
            ),
        ]
        verbose_name = "Camera"
        verbose_name_plural = "Cameras"

    def clean(self):
        super().clean()
        errors = {}
        value = (self.stream_url or "").strip()

        if self.source_type in {self.SourceType.RTSP, self.SourceType.RTSPS}:
            if not value:
                errors["stream_url"] = "A stream URL is required for network cameras."
            else:
                try:
                    parsed = urlsplit(value)
                    hostname = parsed.hostname
                    # Accessing .port also validates malformed port values.
                    _ = parsed.port
                except ValueError:
                    parsed = None
                    hostname = None

                if parsed is None:
                    errors["stream_url"] = "The stream URL is malformed."
                elif parsed.scheme.lower() != self.source_type:
                    errors["stream_url"] = (
                        f"The URL scheme must be {self.source_type} for this source type."
                    )
                elif not hostname:
                    errors["stream_url"] = "The stream URL must contain a valid host."
                elif parsed.username or parsed.password:
                    errors["stream_url"] = (
                        "Do not include usernames or passwords in the stream URL. "
                        "Use the separate encrypted credential fields."
                    )
                elif parsed.fragment:
                    errors["stream_url"] = "URL fragments are not allowed in stream URLs."
        elif self.source_type == self.SourceType.BROWSER and value:
            errors["stream_url"] = (
                "Browser cameras must not provide a server-side stream URL."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def has_stream_credentials(self) -> bool:
        return bool(self.credentials_encrypted)

    def set_stream_credentials(self, username: str, password: str) -> None:
        self.credentials_encrypted = encrypt_camera_credentials(username, password)

    def clear_stream_credentials(self) -> None:
        self.credentials_encrypted = ""

    def build_connection_url(self) -> str:
        """Return an internal RTSP URL with decrypted credentials for OpenCV only."""
        value = (self.stream_url or "").strip()
        if self.source_type == self.SourceType.BROWSER or not value:
            raise ValueError("This camera does not have a server-side network stream.")
        parsed = urlsplit(value)
        if not self.credentials_encrypted:
            return value
        credentials = decrypt_camera_credentials(self.credentials_encrypted)
        username = quote(credentials["username"], safe="")
        password = quote(credentials["password"], safe="")
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{username}:{password}@{host}{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))

    def __str__(self):
        return f"{self.name} ({self.organization.name})"
