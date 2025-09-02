# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays. It uses a series of configuration files and scripts to combine a single long video recording with animated timers and title cards, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file for easy theme changes.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets.
- **Professional Color Grading:** Automatically applies a specified `.cube` LUT to the source video with a color-accurate filter chain for V-Log to Rec.709 conversion.
- **Configurable Audio Processing:** Automatically convert mono microphone tracks to stereo for better playback compatibility.
- **Flexible Overlay Positioning:** Place the timer and exercise titles anywhere on the screen using FFmpeg's positioning expressions in the config file.
- **Configurable Framing:** Choose to either `crop` a center-cut from your source video (preserving aspect ratio) or `scale` it to fit.
- **Automatic Title Casing:** Exercise names are automatically converted to Title Case for a clean, consistent look.
- **Powerful Rendering Options:**
    - **Test Mode:** Generate a fast, low-quality preview to check timings and placement without a full render.
    - **Partial Rendering:** Re-render specific segments of your routine.
    - **Source Trimming:** Extract a specific routine from the middle of a long source video using `--start` and `--end` time commands.
- **High Performance:** The timer generation script is highly optimized, and the assembly script uses GPU-accelerated FFmpeg commands where possible.

## Project Structure

Your project folder should be set up like this:
```
.
├── assets/
│   └── timers/
├── config.yaml
├── create_progress_ring.py
├── assemble_video.py
├── routine.yaml
├── requirements.txt
└── README.md
```

## Setup

### 1. Prerequisites

- **Python 3.8+**
- **FFmpeg:** Must be installed and accessible in your system's PATH. (The full build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) is recommended for Windows).
- An NVIDIA GPU is recommended for speed. If you don't have one, change the `codec` in `config.yaml` to `libx264`.

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Configure Your Style

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, sizes, video resolution, framing method, overlay positions, your color grading LUT, and audio settings.

### Step 2: Define Your Routine

Open or create a `routine.yaml` file. List each exercise with its `name` and `length` in seconds.

### Step 3: Generate Timer Assets

The assembly script needs a pre-made timer video for each unique duration in your routine. For each unique `length` value, run:
```bash
python create_progress_ring.py <duration_in_seconds>
```
**Example Commands:**
```bash
python create_progress_ring.py 45
python create_progress_ring.py 53
```

### Step 4: Assemble the Final Video

The main script has several powerful options for processing your video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> [options]
```

**Options:**
- `--test`: Generate a fast, low-resolution preview.
- `--segments "1,3,5"`: Process only specific segments (1-based index).
- `--start 300`: Start using the source video from the 5-minute mark (300 seconds).
- `--end 1800`: Do not use any footage past the 30-minute mark (1800 seconds).

**Example 1: Full Quality Render**```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```

**Example 2: Fast Test Render of a Single Segment**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test_preview.mp4" --segments 5 --test
```