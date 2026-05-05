"""Extension categories and format compatibility — ported from Helpers.cs."""

AUDIO_EXTENSIONS = {
    "aac", "aif", "aiff", "ape", "dff", "dsf", "flac", "mka", "mp3",
    "m4a", "m4b", "mpc", "oga", "ogg", "opus", "wav", "wma", "wv",
}

VIDEO_EXTENSIONS = {
    "3gp", "3gpp", "avi", "bik", "f4v", "flv", "m2ts", "m4v", "mp4",
    "mts", "mxf", "mpg", "mpeg", "mov", "mkv", "ogv", "qt", "rm",
    "ts", "vob", "webm", "wmv",
}

IMAGE_EXTENSIONS = {
    "arw", "avif", "bmp", "cr2", "dds", "dng", "exr", "heic",
    "ico", "jfif", "jp2", "jpg", "jpeg", "nef", "pbm", "pgm", "png",
    "ppm", "psd", "raf", "tga", "tif", "tiff", "svg", "xcf", "webp",
}

ANIMATED_IMAGE_EXTENSIONS = {"gif"}

DOCUMENT_EXTENSIONS = {
    "csv", "doc", "docx", "epub", "html", "key", "numbers", "odp",
    "ods", "odt", "pages", "pdf", "ppt", "pptx", "rtf", "txt",
    "xls", "xlsx",
}

# Things LibreOffice should handle (everything that isn't pdf-as-pdf or an image).
# pdf is excluded because pdf-as-input goes to ImageMagick (rasterisation path).
OFFICE_EXTENSIONS = {
    "csv", "doc", "docx", "epub", "html", "key", "numbers", "odp",
    "ods", "odt", "pages", "ppt", "pptx", "rtf", "txt", "xls", "xlsx",
}

# Office formats LibreOffice can produce directly (no PDF detour).
# Single source of truth — both factory.py and libreoffice.py read this.
LIBREOFFICE_OUTPUTS = frozenset({"docx", "odp", "ods", "odt", "pptx", "xlsx"})

ALL_INPUT_EXTENSIONS = sorted(
    AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
    | ANIMATED_IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
)

OUTPUT_TYPES = [
    # Audio
    "aac", "flac", "m4a", "mp3", "ogg", "opus", "wav",
    # Video
    "avi", "mkv", "mov", "mp4", "ogv", "webm",
    # Image
    "avif", "bmp", "gif", "ico", "jpg", "png", "tiff", "webp",
    # Document
    "docx", "odp", "ods", "odt", "pdf", "pptx", "xlsx",
]


def get_extension_category(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in AUDIO_EXTENSIONS:
        return "Audio"
    if ext in VIDEO_EXTENSIONS:
        return "Video"
    if ext in IMAGE_EXTENSIONS:
        return "Image"
    if ext in ANIMATED_IMAGE_EXTENSIONS:
        return "Animated Image"
    if ext in DOCUMENT_EXTENSIONS:
        return "Document"
    return "Misc"
