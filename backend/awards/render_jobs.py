"""Spawn-safe entry points: import Django only after the child is initialized."""
from pathlib import Path

_CONTEXT = None


def setup_django():
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()


def init_render_process(departments, template, seals, font_files, media_root=None):
    global _CONTEXT
    if media_root:
        import os
        os.environ["MEDIA_ROOT"] = media_root
    setup_django()
    _CONTEXT = departments, template, seals, font_files


def close_render_process():
    from .ppt_renderer import release_renderer
    release_renderer()


def render_job(payload, number, output_root, make_image, existing_pdf=None):
    from .renderer import image_from_pdf, render_certificate_payload
    if existing_pdf:
        image = Path(output_root) / f"{number}.png"
        image_from_pdf(existing_pdf, image)
        from .integrity import file_digest
        return None, image, file_digest(existing_pdf)
    departments, template, seals, fonts = _CONTEXT
    return render_certificate_payload(payload, number, departments, template, seals, output_root, make_image, fonts)
