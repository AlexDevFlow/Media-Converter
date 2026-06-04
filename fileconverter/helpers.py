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
# txt/csv export with a bare extension; rtf/epub/html need an explicit filter
# name (see libreoffice._LO_EXPORT_FILTERS) because LibreOffice can't resolve
# cross-module export filters from the extension alone.
LIBREOFFICE_OUTPUTS = frozenset({
    "csv", "docx", "epub", "html", "odp", "ods", "odt", "pptx", "rtf", "txt", "xlsx",
})

ALL_INPUT_EXTENSIONS = sorted(
    AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
    | ANIMATED_IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
)

OUTPUT_TYPES = [
    # Audio
    "aac", "ac3", "aiff", "flac", "m4a", "mp3", "ogg", "opus", "wav", "wma",
    # Video
    "avi", "mkv", "mov", "mp4", "ogv", "webm",
    # Image
    "avif", "bmp", "gif", "ico", "jp2", "jpg", "png", "tga", "tiff", "webp",
    # Document
    "csv", "docx", "epub", "html", "odp", "ods", "odt", "pdf", "pptx", "rtf",
    "txt", "xlsx",
]

# Video codecs selectable per-preset for mp4/mkv/mov outputs. The container
# (output_type) is the file extension; the codec is chosen via the preset's
# "video_codec" setting so e.g. H.264 and H.265 can share the .mp4 extension.
VIDEO_CODECS = ["h264", "hevc", "av1", "prores"]


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
