I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support a highly detailed structure, including:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** Controls for color grading, including a `lut_files` key that accepts a list of `.cube` files.
- **`finishing_filters`:** A block for `sharpen`.
- **`progress_ring`:** Settings for the animated timer.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`sound_effects`:** A section to control audio overlays, with a library of effects (file, volume, layout) and rules to trigger them.
- **`background_music` (New):** A section to control background music.
    - **`enabled`**: A boolean to turn the feature on/off.
    - **`master_volume`**: A global volume multiplier for all music.
    - **`music_folder`**: The path to a directory containing audio files. The script must search this directory **recursively**.
    - **`fade_duration`**: A float for the duration (in seconds) of the master fade-in/fade-out on the final concatenated video.
    - **`ducking_enabled`**: A boolean to enable automatic volume reduction of music when a sound effect plays.
    - **`ducking_volume`**: The volume multiplier (e.g., 0.2 for 20%) to which the music is reduced during ducking.
    - **`rules`**: A list of rules that assign specific music to segments, including `triggers` (keywords), a `file` path, and a `mode` key ('loop' or 'continue').
- **`video_output`:** Default resolution, encoder, audio settings, `bit_depth`, and advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output`.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets. Its functionality is stable and does not need to be changed.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags: `--segments`, `--start`, `--end`, `--test`, `--force-render`, `--verbose`, `--config`.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** The script MUST use `ffprobe` to determine the pixel format of the source video and dynamically select the correct pixel format strings for processing.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested with an h264 encoder.
3.  **Explicit Channel Layouts:** The script must prevent FFmpeg from guessing channel layouts. It must be hardcoded to use `-channel_layout mono` for the source video input and `-channel_layout stereo` for the background music input. The sound effect layout should be sourced from the `config.yaml`.
4.  **Advanced Audio Mixing & Ducking:**
    - The script must parse the `background_music` and `sound_effects` sections.
    - It must manage a persistent state for `'continue'` mode music tracks across segments.
    - If `ducking_enabled` is true and both music and a sound effect are present, it must build a `sidechaincompress` audio filter.
    - **Crucially**, it must use the `asplit` filter on the sound effect audio stream to create two copies: one for the `sidechaincompress` input and one to be mixed into the final audio output. This ensures the sound effect is actually heard.
    - It must dynamically build an `amix` filter chain to mix the source audio, (ducked or normal) background music, and sound effects.
5.  **Filter Architecture (GPU-First, then CPU):**
    - The filter graph must begin with GPU scaling (`scale_cuda`), then download the frame for CPU processing (`zscale`, `lut3d`, `unsharp`).
    - Overlays (timer, drawtext) must be performed on the final CPU-processed video stream.
6.  **Robust Final Assembly:** The final concatenation step must copy the video stream but **re-encode the audio** using the `aresample` and `afade` filters (if configured) to guarantee perfect sync and a polished finish.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML`.
- A comprehensive `README.md` file.
- The `prompt.md` file itself for project regeneration.