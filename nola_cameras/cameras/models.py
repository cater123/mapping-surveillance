"""
Camera model for MIT surveillance camera mapping.
"""

import uuid
from io import BytesIO
from pathlib import Path

from ckeditor.fields import RichTextField
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps


def _strip_image_metadata(image_file):
    """
    Re-encode an uploaded image so it carries none of its original metadata —
    notably EXIF GPS geotags, camera/device identifiers, and timestamps that
    could deanonymize whoever submitted the photo.
    """
    image_file.seek(0)
    original = Image.open(image_file)
    original = ImageOps.exif_transpose(original)  # bake in visual orientation before dropping EXIF

    fmt = (original.format or "JPEG").upper()
    if fmt not in ("JPEG", "PNG", "WEBP"):
        fmt = "JPEG"
    mode = original.mode
    if fmt == "JPEG" and mode not in ("RGB", "L"):
        mode = "RGB"

    # A brand-new Image carries no .info dict, so copying only pixel data
    # (not the source image object) drops EXIF/ICC/XMP entirely.
    clean = Image.new(mode, original.size)
    clean.putdata(list(original.convert(mode).getdata()))

    buffer = BytesIO()
    save_kwargs = {"quality": 90} if fmt == "JPEG" else {}
    clean.save(buffer, format=fmt, **save_kwargs)
    buffer.seek(0)

    return ContentFile(buffer.read(), name=Path(image_file.name).name)


class Camera(models.Model):
    """
    Represents a surveillance camera at MIT.
    """

    class Status(models.TextChoices):
        VETTED = "vetted", "Vetted"
        PENDING = "pending", "Pending Review"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    osm_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        help_text="OpenStreetMap node ID (for deduplication and future OSM contribution)",
    )

    # Location information
    cross_road = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nearest intersection, e.g. 'Canal St & Bourbon St'",
    )
    street_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="Specific address if known",
    )
    location = models.PointField(
        help_text="Geographic coordinates (longitude, latitude)",
        srid=4326,
    )
    building = models.CharField(
        max_length=255,
        blank=True,
        help_text="Building name or number, if known, e.g. 'Building 32 (Stata Center)'",
    )
    floor = models.CharField(
        max_length=50,
        blank=True,
        help_text="Floor or level, if indoors, e.g. '3rd floor'",
    )
    nearby_room = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nearby room, unit, or landmark, if known",
    )
    reporter_notes = models.TextField(
        blank=True,
        help_text="Additional notes submitted by the reporter",
    )

    # Camera details
    facial_recognition = models.BooleanField(
        default=False,
        help_text="Does this camera have facial recognition capability?",
    )
    associated_shop = models.CharField(
        max_length=255,
        blank=True,
        help_text="Business name if this is a private camera",
    )

    manufacturer = models.CharField(
        max_length=255,
        blank=True,
        help_text="Camera manufacturer (e.g. 'Neology, Inc.')",
    )
    direction = models.CharField(
        max_length=20,
        blank=True,
        help_text="Camera pointing direction in degrees (0-359) or cardinal",
    )

    # Status and review
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    notes = models.TextField(
        blank=True,
        help_text="Admin notes about this camera",
    )

    # Reporter information
    reported_by = models.CharField(
        max_length=255,
        blank=True,
        help_text="Email or name of person who reported this camera",
    )
    reported_at = models.DateTimeField(default=timezone.now)

    # Vetting information
    vetted_at = models.DateTimeField(null=True, blank=True)
    vetted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vetted_cameras",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-reported_at"]
        verbose_name = "Camera"
        verbose_name_plural = "Cameras"

    def __str__(self):
        return f"Camera {self.id} ({self.get_status_display()})"

    @property
    def latitude(self):
        return self.location.y if self.location else None

    @property
    def longitude(self):
        return self.location.x if self.location else None

    def approve(self, user):
        """Mark this camera as vetted."""
        self.status = self.Status.VETTED
        self.vetted_at = timezone.now()
        self.vetted_by = user
        self.save()

    def reject(self, user):
        """Mark this camera as rejected."""
        self.status = self.Status.REJECTED
        self.vetted_at = timezone.now()
        self.vetted_by = user
        self.save()


def _camera_image_upload_to(instance, filename):
    ext = Path(filename).suffix.lower() or ".jpg"
    n = CameraImage.objects.filter(camera_id=instance.camera_id).count() + 1
    date = timezone.now().strftime("%Y%m%d")
    return f"camera_images/eos-camera-{instance.camera_id}-{date}-{n}{ext}"


class CameraImage(models.Model):
    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class PhotoType(models.TextChoices):
        SURROUNDING = "surrounding", "Surrounding"
        CLOSE_UP    = "close_up",    "Close Up"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camera      = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="images")
    image       = models.ImageField(upload_to=_camera_image_upload_to)
    photo_type  = models.CharField(max_length=30, choices=PhotoType.choices, default=PhotoType.CLOSE_UP)
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    proposed_by = models.CharField(max_length=255, blank=True)
    proposed_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_images"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["photo_type", "-proposed_at"]
        verbose_name = "Camera Image"
        verbose_name_plural = "Camera Images"

    def __str__(self):
        return f"{self.get_photo_type_display()} — {self.camera} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Only re-encode a newly assigned file (not, e.g., a FieldFile already
        # pointing at existing storage, which tests/fixtures may pass as a
        # plain path string).
        if self.image and not self.image._committed:
            self.image = _strip_image_metadata(self.image)
        super().save(*args, **kwargs)

    def approve(self, user):
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.save()

    def reject(self, user):
        self.status = self.Status.REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.save()


class CorrectionProposal(models.Model):
    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending Review"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camera      = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="correction_proposals")
    message     = models.TextField()
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    proposed_by = models.CharField(max_length=255, blank=True)
    proposed_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_corrections"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-proposed_at"]
        verbose_name = "Correction Proposal"
        verbose_name_plural = "Correction Proposals"

    def __str__(self):
        label = self.camera.cross_road or self.camera.street_address or self.camera.associated_shop
        return f"Correction for {label} ({self.get_status_display()})"

    def accept(self, user):
        self.status = self.Status.ACCEPTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.save()

    def reject(self, user):
        self.status = self.Status.REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.save()


class AboutSection(models.Model):
    """Singleton: project About/description text."""

    content = RichTextField(
        help_text="Description shown in the 'About' tab of the info overlay"
    )

    class Meta:
        verbose_name = "About Section"
        verbose_name_plural = "About Section"

    def __str__(self):
        return "About Section"


class Announcement(models.Model):
    """An individual announcement shown in the info overlay."""

    title = models.CharField(max_length=255)
    content = RichTextField()
    published_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        return self.title
