KHIETTRAN Video Color Studio

Standalone offline Windows 10/11 batch video color correction module.

Features:
- Offline AUTO COLOR frame analysis
- Manual exposure, contrast, highlights, shadows, temperature, tint and saturation
- External .cube 3D LUT
- Original, 2K, 4K and 8K output
- H.264 / H.265 HEVC
- NVIDIA NVENC with CPU fallback
- Audio preservation
- Batch processing
- FFprobe output validation

The existing KHIETTRAN AI STUDIO desktop project is not replaced. This module is isolated under video-color-studio/.

Build on Windows with build_windows.bat.
For a fully offline package, place ffmpeg.exe and ffprobe.exe under runtime/ffmpeg/ before building.
