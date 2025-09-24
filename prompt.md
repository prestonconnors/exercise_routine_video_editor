I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support a highly detailed structure, including:
- **`paths`:** Directories for asset output.
- **`opencl`**: A key for the OpenCL device string.
- **`source_video_processing`:** Controls for color grading.
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`.
- **`progress_ring`:** Settings for the animated timer, including a new `trail_color` key (e.g., '#696969').
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`sound_effects`**: A section to control audio overlays. This must include:
    - **`master_volume`**: A global volume multiplier.
    - **`effects`**: A library of sound files, where each effect has a `file` path, `volume` multiplier, and an explicit channel `layout` (e.g., 'stereo').
    - **`rules`**: A list of rules that determine when an effect plays, including `triggers` (keywords or '*' for wildcard), a `start_time` (positive for start, negative for end, or 'random'), and a `play_percent` chance.
- **`video_output`:** Default resolution, encoder, audio settings, a `bit_depth` key, and a `framing_method` key ('crop' or 'scale'). This section must also support advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output`.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets (`.mov` with ProRes and alpha channel) based on styling from `config.yaml`. It is performance-critical and must use a pre-computation and masking technique. Its functionality is stable and does not need to be changed.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags for partial rendering and debugging.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** The script MUST use `ffprobe` to determine the pixel format of the source video and dynamically select the correct pixel format strings.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested.
3.  **FFmpeg Command Generation:** Input trimming must be done with `-ss` and `-to`. It must handle multiple audio inputs and build complex filter graphs.
4.  **Sound Effect Integration:**
    - Must parse the `sound_effects` section from `config.yaml`.
    - For each video segment, it must check the `rules` against the exercise name and roll for the `play_percent` chance.
    - If a rule matches, it must add the sound file as a new FFmpeg input. It **must** use the `layout` key from the config as an *input option* (`-channel_layout`) before the `-i` flag to prevent FFmpeg from guessing.
    - It must dynamically generate an `amix` audio filter chain to mix the source audio with the sound effect. The `adelay` filter must be used to correctly position the sound effect based on the `start_time` (positive, negative, or random).
    - It must intelligently switch its `-map` argument from the source audio (e.g., `0:a:0?`) to the output of the filter chain (e.g., `[final_a]`) when an effect is mixed.
5.  **Filter Architecture (GPU-First, then CPU):**
    - The filter graph must begin with GPU scaling (`scale_cuda`), then download the frame for CPU processing (cropping, LUTs, sharpening).
    - Overlays (timer, drawtext) must be performed on the final CPU-processed video stream.
6.  **Robust Final Assembly:** The final concatenation step must copy the video stream but **re-encode the audio** using the `aresample` filter to guarantee perfect sync.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, new sound effects system, and a detailed workflow with examples for all command-line arguments.
- The `prompt.md` file itself for project regeneration.
