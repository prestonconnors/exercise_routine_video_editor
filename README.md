# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays. It uses a series of configuration files and scripts to combine a single long video recording with animated timers and title cards, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets.
- **Professional Color & Finishing Pipeline:**
  - **Color Grading:** Automatically applies a specified `.cube` LUT with a color-accurate filter chain for V-Log to Rec.709 conversion.
  - **Finishing Filters:** Apply optional, configurable denoising and sharpening for a final professional polish.
- **Configurable Audio Processing:** Automatically convert mono microphone tracks to stereo.
- **Flexible Overlay Positioning:** Place overlays anywhere using FFmpeg's positioning expressions in the config file.
- **Configurable Framing:** Choose to either `crop` a center-cut from your source video (preserving aspect ratio) or `scale` it to fit, with an option for GPU-accelerated scaling.
- **Powerful Rendering Options:**
  - **Test Mode:** Generate a fast, low-quality preview with the `--test` flag to check timings and placement.
  - **Verbose Mode:** See the full FFmpeg command and its live output for deep debugging with the `--verbose` flag.
  - **Partial Rendering:** Re-render specific segments of your routine with the `--segments` flag.
  - **Source Trimming:** Extract a routine from a long source video using `--start` and `--end` time commands.

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
- **FFmpeg:** Must be installed and accessible in your system's PATH. (A custom build via [Media-Autobuild Suite](https://github.com/m-ab-s/media-autobuild_suite) is recommended for enabling optional CUDA filters like `nlmeans_cuda`).
- An NVIDIA GPU is recommended for speed. If you don't have one, change relevant `backend` and `codec` settings in `config.yaml` to `cpu` and `libx264`.

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
**Example:** `python create_progress_ring.py 45`

### Step 4: Assemble the Final Video

The main script has several powerful options for processing your video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> [options]
```

**Options:**
- `--test`: Generate a fast, low-quality preview.
- `--verbose`: Show the full FFmpeg command and its live output.
- `--segments "1,3,5"`: Process only specific segments (1-based index).
- `--start 300`: Start using the source video from the 5-minute mark (300 seconds).
- `--end 1800`: Do not use any footage past the 30-minute mark.

**Example 1: Full Quality Render**
```bash
python assemble_video.py routine.yaml "D:/Video/raw.MOV" "final_video.mp4"
```

**Example 2: Fast Test Render of a Single Segment for Debugging**
```bash
python assemble_video.py routine.yaml "D:/Video/raw.MOV" "test.mp4" --segments 5 --test --verbose
```