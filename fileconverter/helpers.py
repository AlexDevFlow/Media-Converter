"""Extension categories and format compatibility — ported from Helpers.cs."""

AUDIO_EXTENSIONS = {
    "aac", "aiff", "ape", "flac", "mp3", "m4a", "m4b",
    "oga", "ogg", "opus", "wav", "wma",
}

VIDEO_EXTENSIONS = {
    "3gp", "3gpp", "avi", "bik", "flv", "m4v", "mp4",
    "mpg", "mpeg", "mov", "mkv", "ogv", "rm", "ts", "vob", "webm", "wmv",
}

IMAGE_EXTENSIONS = {
    "arw", "avif", "bmp", "cr2", "dds", "dng", "exr", "heic",
    "ico", "jfif", "jpg", "jpeg", "nef", "png", "psd", "raf",
    "tga", "tif", "tiff", "svg", "xcf", "webp",
}

ANIMATED_IMAGE_EXTENSIONS = {"gif"}

DOCUMENT_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "odp", "ods", "odt", "xls", "xlsx",
}

OFFICE_EXTENSIONS = {
    "doc", "docx", "odt", "xls", "xlsx", "ods", "ppt", "pptx", "odp",
}

ALL_INPUT_EXTENSIONS = sorted(
    AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
    | ANIMATED_IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
)

OUTPUT_TYPES = [
    "aac", "avi", "avif", "flac", "gif", "ico", "jpg", "mkv",
    "mp3", "mp4", "ogg", "ogv", "pdf", "png", "wav", "webm", "webp",
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
