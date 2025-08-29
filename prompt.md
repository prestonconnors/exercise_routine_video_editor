I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos. The project should consist of two main Python scripts, a central YAML configuration file, and supporting documentation.

Here are the detailed requirements for each component:

### 1. `config.yaml`

This file must be the single source of truth for all styling and configuration. It should be well-structured and include sections for:
- **Paths:** Asset output directories.
- **Progress Ring Style:** All settings for the animated timer, including its size, colors, stroke widths, and font settings.
- **Text Overlay Styles:** Settings for the exercise name titles, including font, size, color, background box style, and on-screen position.
- **Video Output:** Final video resolution, codec (e.g., `h264_nvenc`), quality, and audio settings.

Crucially, allow for a *different font file* to be specified for the progress ring text vs. the exercise name text.

### 2. `create_progress_ring.py`

This script's purpose is to generate high-quality, reusable animated timer assets.
- **Input:** It should take a single command-line argument: `duration` (in seconds).
- **Configuration:** It must read all styling and animation parameters from the `config.yaml` file.

**Functional Requirements:**
1.  **Generate Frames:** It must programmatically generate a sequence of PNG frames for the animation using the Pillow library.
2.  **FFmpeg Integration:** After generating the frames, it must automatically call FFmpeg to compile the PNG sequence into a single video file (`prores_aw` with `yuva444p10le` pixel format for alpha transparency).
3.  **Cleanup:** After the video is successfully created, the script must automatically delete the temporary PNG frame folder.
4.  **Performance:** The frame generation loop must be highly performant, using an "incremental drawing" method on a persistent canvas to avoid slowdowns on longer durations.

**Visual Requirements for the Animation:**
- The timer must be a circular progress ring that fills up over the specified duration.
- The ring's color should be a gradient, starting with a random color and smoothly transitioning to pure white at the end.
- The ring must have a configurable black border on both its inside and outside edges, with no gaps.
- A numerical countdown (e.g., "10", "9", "8") should be displayed in the center. The number "0" should not be shown; the number should disappear after "1".
- The countdown number must have a configurable black stroke/outline for legibility.
- Behind the number, there must be a semi-transparent, solid black circle background that is perfectly flush with the inner edge of the progress ring.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** It should take three command-line arguments: the path to the `routine.yaml` file, the path to the long source video file, and the path for the final output video.

**Functional Requirements:**
1.  **Read Inputs:** It must parse the `routine.yaml` (a list of exercises with `name` and `length`) and the `config.yaml`.
2.  **Process Sequentially:** It should iterate through the routine and process the source video in segments.
3.  **For Each Segment, It Must:**
    - Trim the source video to the correct start time and duration.
    - Overlay the correct pre-generated timer asset (e.g., `timer_45s.mov`) that was created by the other script. The script should warn the user if a required timer asset is missing.
    - Use FFmpeg's `drawtext` filter to burn the exercise name directly onto the video.
    - The `drawtext` styling (font, size, background box, position) must come from `config.yaml`.
    - The exercise name should automatically wrap if it's too long.
    - The name should only appear on screen for a configured duration (e.g., the first 5 seconds of the segment).
4.  **Final Assembly:** After all segments are processed as temporary video files, the script must concatenate them in the correct order into a single, final output video file.
5.  **Cleanup:** The script must delete all temporary segment files.
6.  **Error Handling:** The script must provide robust error reporting. If any FFmpeg command fails, the script should terminate and print the full, detailed error message from FFmpeg's stderr to the console.

### 4. Documentation

Please provide:
- A `requirements.txt` file listing the necessary Python libraries (`PyYAML` and `Pillow`).
- A `README.md` file explaining the project's purpose, file structure, setup instructions, and a detailed step-by-step workflow for a user.