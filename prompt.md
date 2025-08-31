I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos. The project should consist of two main Python scripts, a central YAML configuration file, and supporting documentation.

Here are the detailed requirements for each component:

### 1. `config.yaml`

This file must be the single source of truth for all styling and configuration. It should be well-structured and include sections for:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** A section to control color grading, with an `apply_lut` boolean flag and a `lut_file` path for V-Log to Rec.709 conversion.
- **`progress_ring`:** All settings for the animated timer, including a `position` block with `x` and `y` keys for FFmpeg expressions (e.g., `(W-w)/2`).
- **`progress_ring.text`:** A sub-section for the countdown number, including a specific `font_file`, font style, a background circle with configurable color/padding, and a `hide_on_zero` flag.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles, including a specific `font_file`, `font_size`, background box style, character wrap width, and `position_x`/`position_y` keys for FFmpeg expressions.
- **`video_output`:** Final video resolution, codec, quality, audio settings, and a key `audio_channels` (set to 1 for mono, 2 for stereo conversion).

### 2. `create_progress_ring.py`

This script's purpose is to generate high-quality, reusable animated timer assets.
- **Input:** It must take a single command-line argument: `duration` (in seconds).
- **Configuration:** It must read all styling parameters from `config.yaml`.

**Functional Requirements:**
1.  **Generate Frames:** Programmatically generate PNG frames for the animation using the Pillow library.
2.  **FFmpeg Integration:** Automatically call FFmpeg to compile the PNG sequence into a `prores_aw` video with `yuva444p10le` pixel format for alpha transparency.
3.  **Cleanup:** Automatically delete the temporary PNG folder upon successful video creation.
4.  **Performance:** The frame generation loop must be highly performant, using an "incremental drawing" method on a persistent canvas.

**Visual Requirements for the Animation:**
- It must be a circular progress ring that fills over time.
- The color must be a gradient, starting with a random color and smoothly transitioning to white.
- It must have a configurable black border on both the inside and outside edges with no gaps.
- A numerical countdown must be displayed in the center. The number "0" must not be shown.
- The countdown number must have a configurable black stroke/outline for legibility.
- A semi-transparent, solid-colored background circle must sit behind the number, perfectly flush with the inner edge of the progress ring.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** It must accept three positional arguments: `routine.yaml`, `source_video`, `output_video`.
- **Optional Arguments:** It must accept optional flags: `--segments`, `--start`, and `--end`.

**Functional Requirements:**
1.  **Read Inputs:** Parse `routine.yaml` and `config.yaml`.
2.  **Timestamp Logic:** Correctly calculate all segment timestamps in the source video, even when a `--start` offset is used.
3.  **For Each Segment, It Must:**
    - Use input-level trimming (`-ss` and `-to` before `-i`) to correctly trim all streams (video and audio) and avoid duration mismatches.
    - Conditionally apply the LUT and color transformation filter chain from `config.yaml`.
    - Conditionally convert mono audio to stereo using the `pan` audio filter if `audio_channels: 2` is set in the config.
    - Overlay the correct pre-generated timer asset. It must warn the user if a required timer is missing but not crash.
    - Use FFmpeg's `drawtext` filter to burn the exercise name, taking all style and position parameters from `config.yaml`. The name must remain on screen for the full segment.
4.  **Final Assembly:** If only one segment is created, it must rename the temporary file to the final output name. If multiple segments are created, it must concatenate them.
5.  **Cleanup:** The script must delete all temporary segment files and the concat list file.
6.  **User Feedback:** The script must provide verbose feedback, indicating the current segment being processed and printing the time taken for each major step.
7.  **Error Handling:** If any FFmpeg command fails, the script must terminate and print the full, detailed error message from FFmpeg's stderr to the console.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project, setup, and a detailed workflow with examples for all command-line arguments.