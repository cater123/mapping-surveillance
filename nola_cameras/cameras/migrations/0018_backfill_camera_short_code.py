import random

from django.db import migrations


def backfill_short_codes(apps, schema_editor):
    Camera = apps.get_model("cameras", "Camera")
    used = set(Camera.objects.exclude(short_code="").values_list("short_code", flat=True))

    for camera in Camera.objects.filter(short_code=""):
        while True:
            code = f"{random.randint(0, 9999):04d}"
            if code not in used:
                used.add(code)
                break
        camera.short_code = code
        camera.save(update_fields=["short_code"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0017_camera_short_code"),
    ]

    operations = [
        migrations.RunPython(backfill_short_codes, noop_reverse),
    ]
