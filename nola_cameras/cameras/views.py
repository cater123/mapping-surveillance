"""
Views for camera mapping application.
"""

import uuid

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .forms import CameraReportForm, CorrectionProposalForm, PhotoProposalForm
from .models import AboutSection, Announcement, Camera, CameraImage, CorrectionProposal

_MOBILE_UA_KEYWORDS = ("mobile", "android", "iphone", "ipad", "ipod")

_MIT_DEFAULT_LAT = 42.3601
_MIT_DEFAULT_LNG = -71.0942
_MIT_DEFAULT_ZOOM = 16


def _build_og_context(camera, request):
    location_label = camera.cross_road or camera.street_address or camera.associated_shop or "unknown location"
    title = f"Surveillance camera {str(camera.id)[:8]}"

    parts = ["MIT surveillance camera"]
    if camera.associated_shop:
        parts.append(f"at {camera.associated_shop}")
    if camera.street_address and camera.street_address != location_label:
        parts.append(f"({camera.street_address})")
    if camera.facial_recognition:
        parts.append("· Facial recognition enabled")
    description = " ".join(parts) + "."

    image_url = None
    first_image = camera.images.filter(status=CameraImage.Status.APPROVED).first()
    if first_image:
        image_url = request.build_absolute_uri(first_image.image.url)

    canonical_url = f"{request.scheme}://{request.get_host()}/?camera={camera.pk}"
    return {"title": title, "description": description, "image_url": image_url, "url": canonical_url}


class MapView(TemplateView):
    """
    Main map view showing all vetted cameras.
    """

    template_name = "map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_count"] = Camera.objects.filter(status=Camera.Status.PENDING).count()
        context["site_info"] = AboutSection.objects.first()
        context["announcements"] = Announcement.objects.filter(is_active=True)
        context["carto_api_key"] = settings.CARTO_API_KEY

        og = None
        camera_uuid = self.request.GET.get("camera", "").strip()
        if camera_uuid:
            try:
                camera_id = uuid.UUID(camera_uuid)
            except ValueError:
                camera_id = None
            if camera_id:
                camera = Camera.objects.filter(pk=camera_id, status=Camera.Status.VETTED).first()
                if camera:
                    og = _build_og_context(camera, self.request)

        context["og"] = og
        return context


class CameraReportView(FormView):
    """
    Public form for submitting new camera sightings.
    """

    template_name = "report.html"
    form_class = CameraReportForm
    success_url = reverse_lazy("report-success")

    def get_template_names(self):
        ua = self.request.META.get("HTTP_USER_AGENT", "").lower()
        if any(kw in ua for kw in _MOBILE_UA_KEYWORDS):
            return ["report_mobile.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            init_lat = float(self.request.GET.get("lat", _MIT_DEFAULT_LAT))
            init_lng = float(self.request.GET.get("lng", _MIT_DEFAULT_LNG))
            init_zoom = int(self.request.GET.get("zoom", _MIT_DEFAULT_ZOOM))
        except (TypeError, ValueError):
            init_lat, init_lng, init_zoom = _MIT_DEFAULT_LAT, _MIT_DEFAULT_LNG, _MIT_DEFAULT_ZOOM
        context["init_lat"] = max(-90.0, min(90.0, init_lat))
        context["init_lng"] = max(-180.0, min(180.0, init_lng))
        context["init_zoom"] = max(1, min(19, init_zoom))
        context["pinned"] = self.request.GET.get("pinned") == "1"
        context["carto_api_key"] = settings.CARTO_API_KEY
        return context

    def form_valid(self, form):
        camera = form.save()
        for picture in form.cleaned_data.get("pictures") or []:
            CameraImage.objects.create(
                camera=camera,
                image=picture,
                status=CameraImage.Status.PENDING,
            )
        return super().form_valid(form)


class ReportSuccessView(TemplateView):
    """
    Success page after camera submission.
    """

    template_name = "report_success.html"


class ProposePhotoView(FormView):
    """
    Public form to propose a photo for an existing vetted camera.
    """

    template_name = "propose_photo.html"
    form_class = PhotoProposalForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.camera = get_object_or_404(Camera, pk=kwargs["camera_id"], status=Camera.Status.VETTED)

    def get_success_url(self):
        return reverse_lazy("propose-photo-success", kwargs={"camera_id": self.camera.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["camera"] = self.camera
        return context

    def form_valid(self, form):
        form.save(camera=self.camera)
        return super().form_valid(form)


class ProposePhotoSuccessView(TemplateView):
    """
    Success page after photo proposal submission.
    """

    template_name = "propose_photo_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["camera"] = get_object_or_404(
            Camera, pk=kwargs["camera_id"], status=Camera.Status.VETTED
        )
        return context


class ProposeCorrectionView(FormView):
    """
    Public form to propose a correction for an existing vetted camera.
    """

    template_name = "propose_correction.html"
    form_class = CorrectionProposalForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.camera = get_object_or_404(Camera, pk=kwargs["camera_id"], status=Camera.Status.VETTED)

    def get_success_url(self):
        return reverse_lazy("propose-correction-success", kwargs={"camera_id": self.camera.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["camera"] = self.camera
        return context

    def form_valid(self, form):
        form.save(camera=self.camera)
        return super().form_valid(form)


class ProposeCorrectionSuccessView(TemplateView):
    """
    Success page after correction proposal submission.
    """

    template_name = "propose_correction_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["camera"] = get_object_or_404(
            Camera, pk=kwargs["camera_id"], status=Camera.Status.VETTED
        )
        return context
