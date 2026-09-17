import tempfile
from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from cameras.forms import CameraReportForm, PhotoProposalForm, _MAX_IMAGE_SIZE_MB, validate_image_file_size
from cameras.models import Camera, CameraImage

from .utils import make_camera, make_image_file

class ImageSizeValidatorTests(TestCase):
    def _mock_image(self, size_mb):
        img = Mock()
        img.size = size_mb * 1024 * 1024
        return img

    def test_accepts_image_within_limit(self):
        validate_image_file_size(self._mock_image(_MAX_IMAGE_SIZE_MB - 1))  # should not raise

    def test_rejects_image_over_limit(self):
        with self.assertRaises(ValidationError):
            validate_image_file_size(self._mock_image(_MAX_IMAGE_SIZE_MB + 1))

    def test_error_message_mentions_limit(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_image_file_size(self._mock_image(_MAX_IMAGE_SIZE_MB + 1))
        self.assertIn(str(_MAX_IMAGE_SIZE_MB), str(ctx.exception))


VALID_DATA = {
    "cross_road": "Massachusetts Ave & Amherst St",
    "latitude": "42.3601",
    "longitude": "-71.0942",
    "website": "",  # honeypot must be empty
}


class CameraReportFormTests(TestCase):
    def test_valid_form_saves_pending_camera(self):
        form = CameraReportForm(data=VALID_DATA)
        self.assertTrue(form.is_valid(), form.errors)
        camera = form.save()
        self.assertEqual(camera.status, Camera.Status.PENDING)
        self.assertIsNotNone(camera.pk)

    def test_honeypot_filled_is_invalid(self):
        data = {**VALID_DATA, "website": "http://spam.com"}
        form = CameraReportForm(data=data)
        self.assertFalse(form.is_valid())

    def test_missing_cross_road_is_valid(self):
        data = {**VALID_DATA, "cross_road": ""}
        form = CameraReportForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_latitude_is_invalid(self):
        data = {**VALID_DATA}
        del data["latitude"]
        form = CameraReportForm(data=data)
        self.assertFalse(form.is_valid())

    def test_optional_fields_are_saved(self):
        data = {
            **VALID_DATA,
            "cross_road": "",
            "building": "Building 32 (Stata Center)",
            "floor": "3rd floor",
            "nearby_room": "Room 204",
            "reporter_notes": "Pointed at the front door.",
        }
        form = CameraReportForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        camera = form.save()
        self.assertEqual(camera.building, "Building 32 (Stata Center)")
        self.assertEqual(camera.floor, "3rd floor")
        self.assertEqual(camera.nearby_room, "Room 204")
        self.assertEqual(camera.reporter_notes, "Pointed at the front door.")

    def test_pictures_creates_camera_images(self):
        from .utils import make_image_file
        form = CameraReportForm(
            data=VALID_DATA,
            files={"pictures": [make_image_file("a.jpg"), make_image_file("b.jpg")]},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["pictures"]), 2)

    def test_oversized_picture_is_invalid(self):
        oversized = Mock()
        oversized.name = "big.jpg"
        oversized.size = (_MAX_IMAGE_SIZE_MB + 1) * 1024 * 1024
        form = CameraReportForm(data=VALID_DATA, files={"pictures": [oversized]})
        self.assertFalse(form.is_valid())

    def test_latitude_out_of_range(self):
        data = {**VALID_DATA, "latitude": "999"}
        form = CameraReportForm(data=data)
        self.assertFalse(form.is_valid())

    def test_longitude_out_of_range(self):
        data = {**VALID_DATA, "longitude": "999"}
        form = CameraReportForm(data=data)
        self.assertFalse(form.is_valid())

    def test_form_creates_point_geometry(self):
        form = CameraReportForm(data=VALID_DATA)
        self.assertTrue(form.is_valid(), form.errors)
        camera = form.save()
        self.assertAlmostEqual(camera.location.y, 42.3601, places=4)
        self.assertAlmostEqual(camera.location.x, -71.0942, places=4)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoProposalFormTests(TestCase):
    def setUp(self):
        self.camera = make_camera()

    def test_valid_form_is_valid(self):
        form = PhotoProposalForm(
            data={"photo_type": CameraImage.PhotoType.CLOSE_UP, "website": ""},
            files={"image": make_image_file()},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_honeypot_filled_is_invalid(self):
        form = PhotoProposalForm(
            data={"photo_type": CameraImage.PhotoType.CLOSE_UP, "website": "spam"},
            files={"image": make_image_file()},
        )
        self.assertFalse(form.is_valid())

    def test_missing_image_is_invalid(self):
        form = PhotoProposalForm(
            data={"photo_type": CameraImage.PhotoType.CLOSE_UP, "website": ""},
        )
        self.assertFalse(form.is_valid())

    def test_save_creates_pending_image_for_camera(self):
        form = PhotoProposalForm(
            data={"photo_type": CameraImage.PhotoType.SURROUNDING, "website": ""},
            files={"image": make_image_file()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        img = form.save(camera=self.camera)
        self.assertEqual(img.status, CameraImage.Status.PENDING)
        self.assertEqual(img.camera, self.camera)
        self.assertEqual(img.photo_type, CameraImage.PhotoType.SURROUNDING)


class CorrectionProposalFormTests(TestCase):
    def setUp(self):
        self.camera = make_camera()

    def test_valid_form_is_valid(self):
        from cameras.forms import CorrectionProposalForm
        form = CorrectionProposalForm(data={"message": "The street address listed is incorrect.", "website": ""})
        self.assertTrue(form.is_valid(), form.errors)

    def test_honeypot_filled_is_invalid(self):
        from cameras.forms import CorrectionProposalForm
        form = CorrectionProposalForm(data={"message": "Wrong type.", "website": "spam"})
        self.assertFalse(form.is_valid())

    def test_missing_message_is_invalid(self):
        from cameras.forms import CorrectionProposalForm
        form = CorrectionProposalForm(data={"message": "", "website": ""})
        self.assertFalse(form.is_valid())

    def test_save_creates_pending_proposal_for_camera(self):
        from cameras.forms import CorrectionProposalForm
        from cameras.models import CorrectionProposal
        form = CorrectionProposalForm(data={"message": "Address is wrong.", "website": ""})
        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save(camera=self.camera)
        self.assertEqual(proposal.status, CorrectionProposal.Status.PENDING)
        self.assertEqual(proposal.camera, self.camera)
