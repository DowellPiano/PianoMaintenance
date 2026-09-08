from io import BytesIO
import logging
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = (640, 480)
THUMBNAIL_MAX_PIXELS = 40_000_000
THUMBNAIL_JPEG_QUALITY = 82


def build_photo_thumbnail(uploaded_file):
    """Build a bounded JPEG derivative without reading the image from storage."""
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as source:
            if source.width * source.height > THUMBNAIL_MAX_PIXELS:
                logger.warning(
                    "Skipped thumbnail for oversized image",
                    extra={"width": source.width, "height": source.height},
                )
                return None
            source.seek(0)
            thumbnail = ImageOps.exif_transpose(source)
            thumbnail.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            if thumbnail.mode in {'RGBA', 'LA'} or 'transparency' in thumbnail.info:
                rgba_thumbnail = thumbnail.convert('RGBA')
                background = Image.new('RGB', rgba_thumbnail.size, color='white')
                background.paste(rgba_thumbnail, mask=rgba_thumbnail.getchannel('A'))
                thumbnail = background
            elif thumbnail.mode != 'RGB':
                thumbnail = thumbnail.convert('RGB')

            output = BytesIO()
            thumbnail.save(
                output,
                format='JPEG',
                quality=THUMBNAIL_JPEG_QUALITY,
                progressive=True,
            )
            return ContentFile(
                output.getvalue(),
                name=f'{uuid.uuid4().hex}.jpg',
            )
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        logger.warning("Could not generate photo thumbnail", exc_info=True)
        return None
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass
