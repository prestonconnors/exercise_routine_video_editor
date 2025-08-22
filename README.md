# Workout Video Automation Script

This project provides a powerful Python script to automate the creation of workout videos. It takes a raw video file and a YAML-based workout routine, and automatically adds professional, dynamic overlays such as timers, exercise titles, and progress bars. The entire visual style is configurable through a separate YAML file, allowing for easy customization without touching the code.

## Features

-   **Dynamic Overlays**: Automatically adds the current exercise name, a countdown timer for each exercise, and a progress bar for the entire workout.
-   **"Next Up" Preview**: Displays a picture-in-picture video of the next exercise in the final seconds of the current one.
-   **Highly Configurable**: All visual elements, including fonts, colors, sizes, positions, and safe margins, are controlled via a clean `config.yaml` file.
-   **Dynamic Backgrounds**: The countdown timer and exercise name backgrounds are randomly colored for each exercise, with configurable transparency.
-   **Performance Modes**: Includes a `--test` flag for extremely fast, low-quality renders and a `--gpu` flag to attempt hardware-accelerated encoding (NVIDIA NVENC).
-   **Robust and Optimized**: Uses efficient libraries like Pillow for drawing dynamic elements to ensure fast performance and avoid common rendering bugs.

## Prerequisites

Before you begin, you must have the following software installed and available in your system's PATH.

1.  **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
2.  **FFmpeg**: This is the core engine for video processing.
    -   **Windows**: Download a build from [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add the `bin` folder to your system's PATH.
3.  **ImageMagick**: This is required for reliable text rendering in MoviePy.
    -   **Windows**: Download and install from the [official website](https://imagemagick.org/script/download.php#windows). **Crucially, during installation, you must check the box that says "Add application directory to your system path".**

You can verify your FFmpeg and ImageMagick installations by opening a **new** terminal and running `ffmpeg -version` and `magick -version`.

## Installation

1.  **Create a Project Folder** and place the `exercise_routine_video_editor.py` script inside it.
2.  **Open a terminal** in your project folder.
3.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    ```
4.  **Activate the virtual environment:**
    -   **Windows (PowerShell):** `.\venv\Scripts\activate`
    -   **macOS/Linux:** `source venv/bin/activate`
5.  **Install the required Python libraries:**
    ```bash
    pip install moviepy PyYAML numpy Pillow
    ```

## Configuration

The script is controlled by two YAML files: one for the workout routine and one for the visual style.

### 1. The Workout Routine File (`workout.yaml`)

This file defines the sequence and duration of exercises.

**Example:**
```yaml
- name: warmup
  length: 45.0
  type: warmup

- name: Calf Raise
  length: 53.0
  type: compound

- name: Plyo Pushup with Chest Tap
  length: 53.0
  type: compound

- name: rest
  length: 60.0
  type: rest

# ... and so on
```

### 2. The Visual Style File (`config.yaml`)

This file controls the entire look and feel of the video overlays. You can create different style files and switch between them using the `--config` flag.

**Example `config.yaml`:**
```yaml
# ---------------------------------------------------------------------------
# Visual Configuration for the Exercise Routine Video Editor
# ---------------------------------------------------------------------------

# --- Safe Margins ---
# The percentage of the screen to use as a buffer from the edges.
safe_margins:
  horizontal_percent: 5
  vertical_percent: 5

# --- Global Font and Color Settings ---
font_file: 'C:/Windows/Fonts/arialbd.ttf'
font_color: 'white'
stroke_color: 'black'

# --- Exercise Name (Top-Left) ---
exercise_name:
  font_file: 'C:/Users/Preston Connors/AppData/Local/Microsoft/Windows/Fonts/Roboto-VariableFont_wdth,wght.ttf'
  position: ['left', 'top']
  font_size: 120
  stroke_width: 2
  background_padding_percent: 20

# --- Countdown Timer (Top-Right) ---
countdown_timer:
  font_file: 'C:/Users/Preston Connors/AppData/Local/Microsoft/Windows/Fonts/Inter-VariableFont_opsz,wght.ttf'
  position: ['right', 'top']
  font_size: 120
  stroke_width: 4
  background_padding_percent: 25
  progress_circle:
    width: 10

# --- Progress Bar (Bottom) ---
progress_bar:
  position: ['center', 'bottom']
  height: 15
  foreground_color: # Orange, RGBA
  background_color:  # Dark Grey, RGBA

# --- "Next Up" Picture-in-Picture (Bottom-Right) ---
next_up_preview:
  position: ['right', 'bottom']
  show_before_end_seconds: 10
  scale: 0.25
  text:
    font_file: 'C:/Users/Preston Connors/AppData/Local/Microsoft/Windows/Fonts/Roboto-VariableFont_wdth,wght.ttf'
    font_size: 30
    stroke_width: 1
```

## Usage

Run the script from your activated virtual environment.

**Standard Quality Render (using CPU):**
```bash
python .\exercise_routine_video_editor.py -y path/to/workout.yaml -i path/to/input.mp4 -o final_video.mp4
```

**Fast Test Render (low-quality, silent):**
```bash
python .\exercise_routine_video_editor.py -y path/to/workout.yaml -i path/to/input.mp4 -o test_video.mp4 --test
```

**GPU-Accelerated Render (NVIDIA):**
```bash
python .\exercise_routine_video_editor.py -y path/to/workout.yaml -i path/to/input.mp4 -o gpu_video.mp4 --gpu
```

**Using a Custom Style File:**
```bash
python .\exercise_routine_video_editor.py -y routine.yaml -i video.mp4 -o dark_style.mp4 --config dark_style.yaml
```