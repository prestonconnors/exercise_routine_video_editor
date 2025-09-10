# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays. It uses a series of configuration files and scripts to combine a single long video recording with animated timers and title cards, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets.
  - The timers feature a gradient fill for the active portion and a configurable static "trail" for the depleted portion.
- **Professional 10-Bit HDR Workflow:**
  - **Dynamic Bit Depth:** Automatically detects the bit depth of your source footage and processes the entire pipeline in 10-bit to preserve color fidelity.
  - **Configurable Output:** Choose to render your final video in 8-bit (SDR) or 10-bit (HDR) via the config file.
  - **Color Grading:** Applies a specified `.cube` LUT with a color-accurate filter chain for V-Log conversion.
  - **Finishing Filters:** Apply optional, configurable denoising and sharpening for a final professional polish.
- **Robust A/V Synchronization:** The final video assembly uses an advanced concatenation method that re-encodes the full audio track to guarantee perfect sync and eliminate any pops or clicks at segment transitions.
- **GPU-First Architecture:** The pipeline is optimized to perform as much work as possible on the GPU (decoding, scaling, denoising, encoding) for maximum performance.
- **Advanced Encoder Tuning:** Fine-tune NVENC settings like lookahead, AQ, and multipass directly from the config for maximum output quality.
- **Powerful Rendering Options:**
  - **Test Mode:** Generate a fast, low-quality preview with the `--test` flag.
  - **Verbose Mode:** See the full FFmpeg command and its live output with the `--verbose` flag.
  - **Partial Rendering:** Re-render specific segments of your routine with the `--segments` flag.
  - **Source Trimming:** Extract a routine from a long source video using `--start` and `--end` time commands.

## Project Structure

Your project folder should be set up like this for the scripts to work correctly:
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
- **FFmpeg:** Must be installed and accessible in your system's PATH. (A custom build via [Media-Autobuild Suite](https://github.com/m-ab-s/media-autobuild_suite) is highly recommended for enabling optional GPU filters like `nlmeans_opencl`).
- **NVIDIA GPU with CUDA Toolkit installed.**

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Configure Your Style

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, sizes, video resolution, output bit depth, framing method, your color grading LUT, and audio settings.

**Note on 10-Bit (HDR):** To render in 10-bit for platforms like YouTube HDR, set `bit_depth: 10` in the `video_output` section. The script will automatically switch to the `hevc_nvenc` (H.265) codec, which is required for HDR delivery.

### Step 2: Define Your Routine

Open or create a `routine.yaml` file. List each exercise or rest period with its `name` and `length` in seconds.

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
- `--verbose` or `-v`: Show the full FFmpeg command and its live output.
- `--segments "1,3,5"`: Process only specific segments (1-based index).
- `--start 300`: Start using the source video from the 5-minute mark.
- `--end 1800`: Do not use any footage past the 30-minute mark.

**Example 1: Full Quality Render of an Entire Routine**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```

**Example 2: Fast Test Render of a Single Segment for Debugging**
This command is perfect for quickly checking the style and placement of your overlays.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test_preview.mp4" --segments 5 --test --verbose
```