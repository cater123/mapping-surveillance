"""
Forms for camera submission.
"""

from django import forms
from django.contrib.gis.geos import Point

from .models import Camera, CameraImage, CorrectionProposal

_MAX_IMAGE_SIZE_MB = 20


def validate_image_file_size(image):
    if image.size > _MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise forms.ValidationError(f"Image too large. Maximum size is {_MAX_IMAGE_SIZE_MB} MB.")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A FileField that accepts multiple uploaded files."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return [single_file_clean(data, initial)] if data else []


class CameraReportForm(forms.ModelForm):
    """
    Form for public camera submissions.
    Includes honeypot field for spam prevention.
    """

    # Hidden honeypot field - should remain empty
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "tabindex": "-1",
            "style": "position: absolute; left: -9999px;",
        }),
        label="",
    )

    latitude = forms.FloatField(
        widget=forms.HiddenInput(),
        min_value=-90,
        max_value=90,
    )
    longitude = forms.FloatField(
        widget=forms.HiddenInput(),
        min_value=-180,
        max_value=180,
    )

    # Not a model field — handled in the view
    pictures = MultipleFileField(required=False)

    class Meta:
        model = Camera
        fields = [
            "cross_road",
            "building",
            "floor",
            "nearby_room",
            "reporter_notes",
        ]
        widgets = {
            "cross_road": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Massachusetts Ave & Amherst St (optional)",
            }),
            "building": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Building 32 (Stata Center) (optional)",
            }),
            "floor": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., 3rd floor (optional)",
            }),
            "nearby_room": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Room 204, near the elevator (optional)",
            }),
            "reporter_notes": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Anything else you'd like to add (optional)",
            }),
        }

    def clean_pictures(self):
        pictures = self.cleaned_data.get("pictures") or []
        for picture in pictures:
            validate_image_file_size(picture)
        return pictures

    def clean(self):
        cleaned_data = super().clean()

        # Check honeypot - if filled, it's likely spam
        if cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")

        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if latitude is not None and longitude is not None:
            cleaned_data["location"] = Point(longitude, latitude, srid=4326)
        else:
            raise forms.ValidationError("Please select a location on the map.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.location = self.cleaned_data["location"]
        instance.status = Camera.Status.PENDING
        if commit:
            instance.save()
        return instance


class PhotoProposalForm(forms.ModelForm):
    """Form for proposing a new photo to an existing vetted camera."""

    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "tabindex": "-1",
            "style": "position: absolute; left: -9999px;",
        }),
        label="",
    )

    class Meta:
        model = CameraImage
        fields = ["image", "photo_type"]
        widgets = {
            "image": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            validate_image_file_size(image)
        return image

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return cleaned_data

    def save(self, camera, commit=True):
        instance = super().save(commit=False)
        instance.camera = camera
        instance.status = CameraImage.Status.PENDING
        if commit:
            instance.save()
        return instance


class CorrectionProposalForm(forms.ModelForm):
    """Form for proposing a correction to an existing vetted camera."""

    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "tabindex": "-1",
            "style": "position: absolute; left: -9999px;",
        }),
        label="",
    )

    class Meta:
        model = CorrectionProposal
        fields = ["message"]
        widgets = {
            "message": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 5,
                "placeholder": "Describe what needs to be corrected or updated (e.g., wrong address, camera removed, type changed...)",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return cleaned_data

    def save(self, camera, commit=True):
        instance = super().save(commit=False)
        instance.camera = camera
        instance.status = CorrectionProposal.Status.PENDING
        if commit:
            instance.save()
        return instance
