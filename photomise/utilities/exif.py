from io import BytesIO

import pendulum
import piexif
import pillow_heif
from PIL import Image, ImageEnhance


def extract_exif_info(image_path: str) -> dict:
    return piexif.load(image_path)


def convert_to_degrees(value) -> float:
    d = value[0][0] / value[0][1]
    m = value[1][0] / value[1][1]
    s = value[2][0] / value[2][1]
    return d + (m / 60.0) + (s / 3600.0)


def deg_to_dms_rational(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = (deg - d - m / 60) * 3600
    return [(d, 1), (m, 1), (int(s * 100), 100)]


def extract_gps(tags: dict) -> tuple:
    gps_info = tags.get("GPS", {})

    gps_latitude = gps_info.get(piexif.GPSIFD.GPSLatitude)
    gps_latitude_ref = gps_info.get(piexif.GPSIFD.GPSLatitudeRef)
    gps_longitude = gps_info.get(piexif.GPSIFD.GPSLongitude)
    gps_longitude_ref = gps_info.get(piexif.GPSIFD.GPSLongitudeRef)

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = convert_to_degrees(gps_latitude)
        if gps_latitude_ref != b"N":
            lat = -lat
        lon = convert_to_degrees(gps_longitude)
        if gps_longitude_ref != b"E":
            lon = -lon
        return lat, lon
    else:
        return None, None


def compress_image(
    image_path: str,
    quality: int = 80,
    max_dimension: int = 1200,
    rotation_angle: int = 0,
    brightness: float = 1.0,
    contrast: float = 1.0,
    color: float = 1.0,
    sharpness: float = 1.0,
    show: bool = False,
):
    """Compress and process an image with various enhancement options.

    This function takes an image file, compresses it, and applies various image processing
    operations including rotation, resizing, and enhancement of visual properties.

    Args:
        image_path (str): Path to the input image file.
        quality (int, optional): JPEG compression quality (1-100). Defaults to 80.
        max_dimension (int, optional): Maximum allowed dimension (width/height) in pixels. Defaults to 1200.
        rotation_angle (int, optional): Rotation angle in degrees. Defaults to 0.
        brightness (float, optional): Brightness enhancement factor. Defaults to 1.0.
        contrast (float, optional): Contrast enhancement factor. Defaults to 1.0.
        color (float, optional): Color enhancement factor. Defaults to 1.0.
        sharpness (float, optional): Sharpness enhancement factor. Defaults to 1.0.
        show (bool, optional): If True, displays the processed image. Defaults to False.

    Returns:
        BytesIO: A BytesIO object containing the compressed image in JPEG format.

    Raises:
        Exception: If there's an error during image processing, prints error message.
    """
    try:
        if image_path.lower().endswith(".heic"):
            heif_file = pillow_heif.read_heif(image_path)
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
        else:
            image = Image.open(image_path)

        # Convert HEIC to RGB mode if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        img_io = BytesIO()

        if rotation_angle:
            image = image.rotate(float(rotation_angle), expand=True)

        width, height = image.size

        if width > max_dimension or height > max_dimension:
            if width > height:
                scale_factor = max_dimension / width
            else:
                scale_factor = max_dimension / height

            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.LANCZOS)

        image = enhance_image(
            image,
            brightness,
            contrast,
            color,
            sharpness,
        )

        image.save(img_io, format="JPEG", optimize=True, quality=quality)
        if show:
            image.show()

        img_io.seek(0)

        return img_io
    except Exception as e:
        print(f"Error compressing image: {e}")


def enhance_image(
    image: Image.Image,
    brightness: float = 1.0,
    contrast: float = 1.0,
    color: float = 1.0,
    sharpness: float = 1.0,
) -> Image.Image:

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(brightness)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)

    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(color)

    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(sharpness)

    return image


def extract_datetime(tags: dict) -> pendulum:
    exif_info = tags.get("Exif", {})
    date_taken = exif_info.get(piexif.ExifIFD.DateTimeOriginal)

    if date_taken:
        date_taken_str = date_taken.decode("utf-8")
        date_taken_formatted = date_taken_str.replace(":", "-", 2)
        dt = pendulum.parse(date_taken_formatted)

        return dt
    else:
        return None


def get_image_aspect_ratio(image_path: str) -> tuple:
    try:
        exif_dict = piexif.load(image_path)
        image_width = exif_dict["0th"][piexif.ImageIFD.ImageWidth]
        image_height = exif_dict["0th"][piexif.ImageIFD.ImageLength]
        return (image_width, image_height)
    except (piexif.InvalidImageDataError, KeyError, TypeError):
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return (width, height)
        except (OSError, IOError):
            return None, None
