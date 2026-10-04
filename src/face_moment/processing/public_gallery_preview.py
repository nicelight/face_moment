"""Processing-owned on-demand gallery JPEG; no derivative/state publication."""
from __future__ import annotations

from io import BytesIO
from PIL import Image, ImageOps


def render_public_gallery_preview(original: bytes) -> bytes:
    """EXIF-orient and encode width640, including small historical originals."""
    with Image.open(BytesIO(original), formats=['JPEG']) as source:
        oriented = ImageOps.exif_transpose(source)
        height = max(1, round(oriented.height * 640 / oriented.width))
        resized = oriented.convert('RGB').resize((640, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        resized.save(output, 'JPEG', quality=85)
        return output.getvalue()
