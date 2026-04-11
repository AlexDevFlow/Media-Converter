"""GIF conversion pipeline — ported from ConversionJob_Gif.cs.

For image inputs: ImageMagick converts to PNG first, then FFmpeg creates the GIF.
For video inputs: FFmpeg handles it directly with palette generation.
"""

from __future__ import annotations
import os
import tempfile

from fileconverter.helpers import IMAGE_EXTENSIONS, ANIMATED_IMAGE_EXTENSIONS
from fileconverter.jobs.base import ConversionJob
from fileconverter.jobs.ffmpeg import FFmpegJob
from fileconverter.jobs.imagemagick import ImageMagickJob
from fileconverter.path_helpers import generate_unique_path
from fileconverter.presets import ConversionPreset


class GifJob(ConversionJob):
    def __init__(self, preset: ConversionPreset, input_path: str):
        super().__init__(preset, input_path)

    def _convert(self) -> None:
        ext = os.path.splitext(self.input_path)[1].lower().lstrip(".")
        is_image = ext in IMAGE_EXTENSIONS or ext in ANIMATED_IMAGE_EXTENSIONS

        if is_image and ext != "png":
            # Step 1: Convert image to PNG via ImageMagick
            self.user_state = "Preparing image..."
            self.progress = 0.1

            tmp_png = generate_unique_path(
                os.path.join(tempfile.gettempdir(), os.path.basename(self.input_path) + ".png")
            )
            try:
                png_preset = ConversionPreset(
                    name="_tmp_png",
                    output_type="png",
                    input_types=[ext],
                    settings=self.preset.settings.copy(),
                )
                img_job = ImageMagickJob(png_preset, self.input_path)
                img_job.output_paths = [tmp_png]
                img_job._convert_cmd = ImageMagickJob._find_convert()
                img_job._convert()

                self.progress = 0.3

                # Step 2: PNG → GIF via FFmpeg
                self.user_state = "Creating GIF..."
                ff_job = FFmpegJob(self.preset, tmp_png)
                ff_job.output_paths = self.output_paths
                ff_job._build_arguments()
                ff_job._convert()

                self.progress = 1.0
            finally:
                if os.path.exists(tmp_png):
                    os.remove(tmp_png)
        else:
            # Video or PNG → GIF directly via FFmpeg
            self.user_state = "Creating GIF..."
            ff_job = FFmpegJob(self.preset, self.input_path)
            ff_job.output_paths = self.output_paths
            ff_job._build_arguments()
            ff_job._convert()
            self.progress = 1.0
