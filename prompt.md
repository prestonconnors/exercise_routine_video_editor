I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support a highly detailed structure, including:
- **`paths`:** Directories for asset output.
- **`opencl`**: A key for the OpenCL device string.
- **`source_video_processing`:** Controls for color grading.
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`.
- **`progress_ring`:** Settings for the animated timer, including a new `trail_color` key (e.g., '#696969').
- **`progress_ring.text`:** Settings for the countdown number.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`video_output`:** Default resolution, encoder, audio settings, a `bit_depth` key, and a `framing_method` key ('crop' or 'scale'). This section must also support advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output`.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets (`.mov` with ProRes and alpha channel) based on styling from `config.yaml`.
- **Input:** Must take a single `duration` (in seconds) as a command-line argument.
- **Performance (CRITICAL):** The animation **must** be generated using a high-performance **pre-computation and masking** technique.
  1.  Before the main loop, the script must fully render two separate image layers into memory: a static "trail" layer (the full, depleted ring) and a "gradient" layer (the full, completed, color-gradient ring).
  2.  Inside the main loop, for each frame, it must generate a simple black-and-white mask.
  3.  It will then create the final frame by compositing the two pre-rendered layers using the mask. This ensures a constant-time, high-speed render for every frame.
- **Functionality:** It must compile the final PNG sequence into a `.mov` file with FFmpeg and clean up temporary frames.
- **Visuals:** It must create a bordered, gradient-colored circular progress ring with a configurable static-colored trail. It must also have a countdown number with a background circle.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags for partial rendering and debugging.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** The script MUST use `ffprobe` to determine the pixel format of the source video and dynamically select the correct pixel format strings for every filter and encoder setting throughout the pipeline.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested.
3.  **FFmpeg Command Generation:** Must correctly initialize OpenCL hardware devices if an OpenCL filter is enabled. Input trimming must be done with `-ss` and `-to`. The audio channel layout of the source should be explicitly set.
4.  **Filter Architecture (GPU-First, then CPU):**
    - The filter graph must begin with GPU scaling (`scale_cuda`), then download the frame for CPU processing.
    - CPU operations (cropping, LUT application, sharpening) must be performed in a stable, sequential chain.
    - Optional GPU denoising (with `nlmeans_opencl`) can be applied after the CPU chain via a `hwupload`/`hwdownload` round-trip.
    - Overlays (timer, drawtext) must be performed on the final CPU-processed video stream for maximum stability.
5.  **Robust Final Assembly:** The final concatenation step must copy the video stream but **re-encode the audio** using the `aresample` filter to guarantee perfect sync and eliminate audio artifacts.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, and a detailed workflow with examples for all command-line arguments.
- The `prompt.md` file itself for project regeneration.