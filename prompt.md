I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support the following structure:
- **`paths`:** Directories for asset output.
- **`opencl`**: A key for the OpenCL device string.
- **`source_video_processing`:** Controls for color grading.
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`.
- **`progress_ring`:** Settings for the animated timer.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`video_output`:** Default resolution, codec, and audio settings, plus a `bit_depth` key and `framing_method` key ('crop' or 'scale'). This section must also support advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output` for fast previews.

### 2. `create_progress_ring.py`
This script must generate reusable, animated timer assets (`.mov` with ProRes and alpha channel) based on styling from `config.yaml`. It must be performant and clean up its temporary PNG frames automatically.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and several optional flags for partial rendering and debugging (`--segments`, `--start`, `--end`, `--test`, `--verbose`).

**Functional Requirements (CRITICAL):**
1.  **Dynamic Bit Depth Pipeline:** The script MUST begin by using `ffprobe` to determine the pixel format of the source video and dynamically select the correct pixel format strings for every filter and encoder setting throughout the pipeline.
2.  **Smart Codec Handling:** The script must automatically switch the encoder to `hevc_nvenc` if a `bit_depth` of 10 is requested.
3.  **FFmpeg Command Generation:**
    - The command must start with `-hwaccel cuda -hwaccel_output_format cuda` and other optimizations.
    - It must explicitly set the source audio channel layout using the `-channel_layout` input option before `-i`.
    - If OpenCL is enabled, it must include `-init_hw_device` and `-filter_hw_device` before the inputs.
    - Input trimming must be done with `-ss` and `-to`.
4.  **Filter Architecture (GPU-First, then CPU):**
    - **Chain 1:** Start with `[0:v]`, use `scale_cuda` on the GPU first, then `hwdownload` the frame.
    - **Chain 2:** On the CPU, apply a series of filters in order: `crop` (with even-aligned offsets), the `zscale/lut3d/zscale` color pipeline, and the CPU `unsharp` filter.
    - **Chain 3 (Optional):** If OpenCL denoising is enabled, the result of the CPU chain is `hwupload`ed, processed by `nlmeans_opencl`, and `hwdownload`ed back.
    - **Chain 4 & 5:** All overlays (timer, drawtext) must be performed on the final CPU-processed video stream for maximum stability.
5.  **Robust Final Assembly:** If only one segment is created, rename the temp file. If multiple segments are created, the script must use a **robust concatenation command** that copies the video stream (`-c:v copy`) but **re-encodes the audio stream** (`-c:a aac`). This command must use `-fflags +genpts`, `-avoid_negative_ts make_zero`, and the `aresample` audio filter (`-af aresample=...`) to ensure a perfectly continuous and synchronized final output.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, and a detailed workflow with examples for all command-line arguments.
- The `prompt.md` file itself for project regeneration.