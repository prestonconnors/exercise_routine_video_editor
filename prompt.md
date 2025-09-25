I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support a highly detailed structure, including:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** Controls for color grading, including a `lut_files` key that accepts a list of `.cube` files.
- **`finishing_filters`:** A block for `sharpen`.
- **`progress_ring`:** Settings for the animated timer.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`sound_effects`:** A section to control audio overlays, with a library of effects and rules to trigger them.
- **`background_music`:** A section to control background music, with recursive folder search, master volume, global fades, sidechain compression (`ducking`), and rule-based track assignment (`loop` or `continue` modes).
- **`video_output`:** Default resolution, encoder, audio settings, `bit_depth`, and advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output`.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets. Its functionality is stable and does not need to be changed.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags: `--segments`, `--start`, `--end`, `--test`, `--force-render`, `--verbose`, `--config`.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** Must use `ffprobe` to determine the source pixel format and dynamically select correct pixel formats for processing.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested with an h264 encoder.
3.  **Explicit Channel Layouts:** Must hardcode channel layouts for all audio inputs (`mono` for source, `stereo` for music, and configurable for sound effects) to prevent FFmpeg from guessing.
4.  **Advanced Audio Mixing & Ducking:**
    - Must build a complex audio filter graph that can manage source audio, background music, and sound effects simultaneously.
    - If ducking is enabled, it must use the `asplit` filter to clone the sound effect stream, using one copy for the `sidechaincompress` trigger and the other to be mixed into the final output.
    - Must dynamically build a final `amix` filter to combine all audible audio streams.
5.  **Filter Architecture (GPU-First):** Must perform GPU-native scaling (`scale_cuda`) before downloading the frame for CPU-based filters (`zscale`, `lut3d`, `unsharp`) and overlays (`drawtext`).
6.  **Robust Final Assembly:** The concatenation step must copy the video stream but re-encode the audio with `aresample` and `afade` filters to guarantee sync and a polished finish.

### 4. `download_music_from_youtube_playlists.py` (New)

This is a utility script to acquire high-quality audio.
- **Purpose:** Downloads audio from YouTube URLs (single video or playlist) for use as background music in the main pipeline.
- **Strategy:** Employs a quality-first approach:
    - If the best available audio is in AAC/M4A format, it keeps it as-is to avoid transcoding.
    - Otherwise (e.g., Opus/WebM), it performs a single lossless conversion to FLAC.
- **Features:** Must embed metadata and the video thumbnail as cover art into the final audio file (`.m4a` or `.flac`).
- **Dependencies:** Requires `yt-dlp` to be installed and `ffmpeg` to be on the system PATH.
- **Input:** Must accept positional arguments for the output directory and one or more YouTube URLs.

### 5. Documentation

Provide:
- A `requirements.txt` file listing:
  ```
  PyYAML
  Pillow
  yt-dlp
  mutagen
  ```
- A comprehensive `README.md` file covering both the video generator and the new music downloader utility.
- The `prompt.md` file itself for project regeneration.