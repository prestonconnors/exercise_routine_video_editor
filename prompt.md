I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos. The project should consist of two main Python scripts, a central YAML configuration file, and supporting documentation.

Here are the detailed requirements for each component:

### 1. `config.yaml`

This file must be the single source of truth for all styling and configuration. It must include sections for:
- **`paths`:** Directories for asset output.
- **`opencl`**: A key for the OpenCL device string (e.g., "0.0").
- **`source_video_processing`:** Controls for color grading (`apply_lut` and `lut_file` path).
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`, each with an `enabled` flag and strength/amount. The `denoise` block must support a `backend` key ('opencl' or 'cpu').
- **`progress_ring`:** Settings for the animated timer, including a `position` block with `x` and `y` keys for FFmpeg expressions.
- **`progress_ring.text`:** A sub-section for the countdown number, including a specific `font_file`, font style, a `background_circle` with configurable color/padding, and a `hide_on_zero` flag.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles, including a specific `font_file`, `font_size`, background box style, character wrap width, and `position_x`/`position_y` keys.
- **`video_output`:** Default resolution, codec, quality, audio settings, an `audio_channels` key, and a `framing_method` key ('crop' or 'scale').
- **`test_mode_settings`:** A section that overrides keys from `video_output` for fast previews.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets.
- **Input:** Must take a single command-line argument: `duration` (in seconds).
- **Functionality:** It must generate a PNG sequence using Pillow, compile it into a `prores_aw` video with FFmpeg, and delete the temporary frames.
- **Performance:** The frame generation loop must use an efficient "incremental drawing" method.
- **Visuals:** It must create a bordered, gradient-colored circular progress ring with a countdown number inside. The number must be backed by a semi-transparent circle that is perfectly flush with the inner ring and disappear after "1".

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`.
- **Optional Arguments:** Must accept optional flags: `--segments`, `--start`, `--end`, `--test`, and `--verbose`.

**Functional Requirements:**
1.  **Read Inputs:** Parse the `routine.yaml` and `config.yaml`.
2.  **Timestamp Logic:** Correctly calculate all segment timestamps in the source video, even when a `--start` offset is used.
3.  **For Each Segment, It Must:**
    - Use **input-level trimming** (`-ss` and `-to`) and **hardware acceleration** (`-hwaccel cuda -hwaccel_output_format cuda`) for the source video.
    - **OpenCL Initialization:** If OpenCL denoising is enabled, the script MUST prepend `-init_hw_device` and `-filter_hw_device` to the FFmpeg command list *before* the inputs.
    - **Stable Filter Architecture:** The filter chain must be built in a stable, segregated manner.
        a. The main video must be downloaded (`hwdownload`), and all CPU-based filters (LUT, Crop, Sharpen) must be applied in a single chain.
        b. If OpenCL denoising is enabled, the result of the CPU chain must then be uploaded (`hwupload`), denoised (`nlmeans_opencl`), and downloaded back (`hwdownload`) in a separate, self-contained chain.
        c. All overlays (timer, text) must be applied on the final CPU-processed video stream for maximum compatibility.
    - **Automatic Title Casing:** The exercise name must be automatically converted to Title Case.
4.  **Final Assembly:** If only one segment is created, it must rename the temporary file. Otherwise, it must concatenate the segments.
5.  **Cleanup:** Must delete all temporary files.
6.  **User Feedback & Error Handling:** Must provide verbose feedback, time each major step, and if any FFmpeg command fails, terminate and print the full error message from FFmpeg's stderr.
7.  **`argparse` Correction:** The argument parser must use `parser.add_argument()` for all flags, including boolean flags like `--test` (`action="store_true"`), and correctly parse comma-separated strings with `args.segments.split(',')`.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, and a detailed workflow with examples for all command-line arguments.
- The `prompt.md` file itself for project regeneration.