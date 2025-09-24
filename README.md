# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays and sound effects. It uses a series of configuration files and scripts to combine a single long video recording with animated timers, title cards, and rule-based audio cues, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file.
- **Rule-Based Sound Effects:**
  - Define a library of sound effects with individual volume and channel layout settings.
  - Create rules to automatically play sounds based on keywords in the exercise name.
  - Trigger effects to play at specific times (e.g., 4 seconds from the end) or at random.
  - Set a percentage chance for a sound to play, adding variety to your videos.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets with configurable colors.
- **Professional 10-Bit HDR Workflow:**
  - **Dynamic Bit Depth:** Automatically detects the bit depth of your source footage and processes the entire pipeline in 10-bit to preserve color fidelity.
  - **Color Grading:** Applies a specified `.cube` LUT for accurate V-Log conversion.
- **Robust A/V Synchronization:** The final assembly uses an advanced concatenation method and a sophisticated `amix` audio filter to seamlessly blend sound effects with the source audio, guaranteeing perfect sync.
- **GPU-First Architecture:** The pipeline is optimized to perform as much work as possible on the GPU (decoding, scaling, encoding) for maximum performance.
- **Advanced Encoder Tuning:** Fine-tune NVENC settings like lookahead, AQ, and multipass directly from the config for maximum output quality.
- **Powerful Rendering Options:**
  - **Test Mode:** Generate a fast, low-quality preview with the `--test` flag.
  - **Verbose Mode:** See the full FFmpeg command and its live output with the `--verbose` flag.
  - **Partial Rendering:** Re-render specific segments of your routine with the `--segments` flag.
  - **Source Trimming:** Extract a routine from a long source video using `--start` and `--end`.

## Project Structure

Your project folder should be set up like this for the scripts to work correctly:
```
.
├── assets/
│   ├── sounds/  <-- Place your .wav or .mp3 files here
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
- **FFmpeg:** Must be installed and accessible in your system's PATH.
- **NVIDIA GPU with CUDA Toolkit installed.**

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Configure Your Style

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, video resolution, your color grading LUT, and audio settings.

### Step 2: (Optional) Add Sound Effects

1.  Place your sound effect files (e.g., `swoosh.wav`) in the `assets/sounds/` directory.
2.  Open `config.yaml` and configure the `sound_effects` section.
    -   Define each audio file in the `effects` library, giving it a name, path, volume, and channel layout.
    -   Create `rules` to determine when each effect should play.

### Step 3: Define Your Routine

Open or create a `routine.yaml` file. List each exercise or rest period with its `name` and `length` in seconds.

### Step 4: Generate Timer Assets

The assembly script needs a pre-made timer video for each unique duration in your routine. For each unique `length` value, run:
```bash
python create_progress_ring.py <duration_in_seconds>```
**Example:** `python create_progress_ring.py 45`

### Step 5: Assemble the Final Video

The main script has several powerful options for processing your video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> [options]
```

**Example 1: Full Quality Render of an Entire Routine**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```

**Example 2: Fast Test Render of a Single Segment for Debugging**
This command is perfect for quickly checking the style, overlays, and sound effect timing.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test_preview.mp4" --segments 5 --test --verbose
```