I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos. The project should consist of two main Python scripts, a central YAML configuration file, and supporting documentation.

Here are the detailed requirements for each component:

### 1. `config.yaml`

This file must be the single source of truth for all styling and configuration. It should be well-structured and include sections for:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** A section to control color grading, with an `apply_lut` boolean flag and a `lut_file` path for V-Log to Rec.709 conversion.
- **`progress_ring`:** All settings for the animated timer, including a `position` block with `x` and `y` keys for FFmpeg expressions (e.g., `(W-w)/2`).
- **`progress_ring.text`:** A sub-section for the countdown number, including a specific `font_file`, font style, a background circle with configurable color/padding, and a `hide_on_zero` flag.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles, including a specific `font_file`, `font_size`, background box style, character wrap width, and `position_x`/`position_y` keys for FFmpeg expressions.
- **`video_output`:** Final video resolution, codec (e.g., `h264_nvenc`), quality, and audio settings.

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
- The countdown number must have a configurable black stroke/outline.
- A semi-transparent, solid-colored background circle must sit behind the number, perfectly flush with the inner edge of the progress ring.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** It must accept three positional arguments: `routine.yaml`, `source_video`, `output_video`.
- **Optional Arguments:** It must accept optional flags: `--segments` (for partial renders), `--start` (to offset the start time in the source video), and `--end` (to cap the end time in the source video).

**Functional Requirements:**
1.  **Read Inputs:** It must parse the `routine.yaml` and `config.yaml`.
2.  **Process Sequentially:** It must iterate through the routine, correctly calculating the timestamps for each segment, even when using a `--start` offset.
3.  **For Each Segment, It Must:**
    - Conditionally apply the LUT and color transformation filter chain from `config.yaml` to the source video.
    - Trim the source video to the correct calculated start and end times.
    - Overlay the correct pre-generated timer asset. It must warn the user if a required timer is missing but not crash.
    - Use FFmpeg's `drawtext` filter to burn in the exercise name, taking all style and position parameters from `config.yaml`.
    - The exercise name must remain on screen for the full duration of the segment.
4.  **Final Assembly:** If multiple segments are created, concatenate them. If only one segment is created, it should rename the temporary file instead of concatenating.
5.  **Cleanup:** The script must delete all temporary segment files.
6.  **User Feedback:** The script must provide verbose feedback in the console, indicating which segment is being processed and printing the time taken for each major step (encoding, concatenation, total).
7.  **Error Handling:** If any FFmpeg command fails, the script must terminate and print the full, detailed error message from FFmpeg's stderr to the console.

### 4. Documentation

Please provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, and a detailed workflow with examples for all command-line arguments.