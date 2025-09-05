I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos. The project should consist of two main Python scripts, a central YAML configuration file, and supporting documentation.

Here are the detailed requirements for each component:

### 1. `config.yaml`

This must be the single source of truth for all styling and configuration. It must include sections for:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** Controls for color grading, with an `apply_lut` boolean and a `lut_file` path.
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`, each with an `enabled` flag, `strength`/`luma_amount`, and a `backend` key (`cpu`, `cuda`, `opencl`).
- **`progress_ring`:** Settings for the animated timer, including a `position` block with `x` and `y` keys for FFmpeg expressions.
- **`progress_ring.text`:** A sub-section for the countdown number, with a specific `font_file`, font style, a `background_circle` with configurable color/padding, and a `hide_on_zero` flag.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles, with a specific `font_file`, `font_size`, background box style, character wrap width, and `position_x`/`position_y` keys.
- **`video_output`:** Default resolution, codec, quality, audio settings, an `audio_channels` key, and a `framing_method` key ('crop' or 'scale') with a corresponding `framing_backend`.
- **`test_mode_settings`:** A section that overrides keys from `video_output` for fast, low-quality previews.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets.
- **Input:** Must take a `duration` (in seconds) as a command-line argument.
- **Configuration:** Must read all styling parameters from `config.yaml`.
- **Functionality:** It must generate a PNG sequence using Pillow, compile it into a `prores_aw` video with FFmpeg, and delete the temporary frames.
- **Performance:** The frame generation loop must use an efficient "incremental drawing" method.
- **Visuals:** It must create a bordered, gradient-colored circular progress ring with a countdown number inside. The number should have a stroke, be backed by a semi-transparent circle flush with the inner ring, and disappear after "1".

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`.
- **Optional Arguments:** Must accept optional flags: `--segments`, `--start`, `--end`, `--test`, and `--verbose`.

**Functional Requirements:**
1.  **Read Inputs:** Parse `routine.yaml` and `config.yaml`.
2.  **Timestamp Logic:** Correctly calculate all segment timestamps, even with a `--start` offset.
3.  **For Each Segment, It Must:**
    - Use **input-level trimming** (`-ss` and `-to`) to correctly trim all streams simultaneously. The filter chain must only use `setpts=PTS-STARTPTS` and not a redundant `trim` filter.
    - Conditionally apply the LUT using a color-accurate `zscale` filter chain that correctly handles full vs. limited color range for V-Log footage.
    - Conditionally apply denoise and sharpen filters, respecting the `backend` key and using the correct FFmpeg parameter names for *both* CPU (`nlmeans=s`, `unsharp=lx:ly:la`) and CUDA (`nlmeans_cuda=strength`, `unsharp_cuda=la`).
    - Check the `framing_method` and use the `crop` filter or the correct `scale`/`scale_cuda` filter based on the `framing_backend` setting.
    - Conditionally convert mono audio to stereo using the `pan` audio filter.
    - Overlay the correct pre-generated timer asset.
    - Automatically convert the exercise name to Title Case and use `drawtext` to burn it onto the video for the full segment duration.
4.  **Final Assembly:** If one segment is created, it must rename the temporary file. Otherwise, it must concatenate the segments.
5.  **Cleanup:** Must delete all temporary files.
6.  **User Feedback & Error Handling:** Must provide verbose feedback, time each major step, and if any FFmpeg command fails, terminate and print the full error message from FFmpeg's stderr.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project, setup, and a detailed workflow with examples for all command-line arguments.
- The `prompt.md` file itself for project regeneration.