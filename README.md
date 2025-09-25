# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays, sound effects, and background music. It uses a series of configuration files and scripts to combine a single long video recording with animated timers, title cards, and rule-based audio cues, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file.
- **Efficient Re-rendering:** The pipeline automatically detects and reuses previously rendered video segments, only encoding new or changed portions.
- **Rule-Based Sound Effects:** Define a library of sound effects and create rules to automatically play sounds based on keywords in the exercise name.
- **Dynamic Background Music:**
  - Automatically select random music from a library folder **and all its subfolders**.
  - Create rules to assign specific music tracks to exercises (e.g., high-energy music for intense sets, calm music for rests).
  - Music can either loop for a segment (`mode: loop`) or play continuously across multiple segments (`mode: continue`).
  - **Audio Ducking:** Professional-grade feature that automatically lowers the music volume when a sound effect plays, ensuring clarity.
  - **Global Fade:** Apply an automated fade-in at the beginning and fade-out at the end of the final video for a polished finish.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** The `create_progress_ring.py` script automatically generates high-quality, reusable animated timer assets.
- **Professional 10-Bit HDR Workflow:**
  - **Dynamic Bit Depth:** Automatically detects the bit depth of your source footage and processes the entire pipeline in 10-bit to preserve color fidelity.
  - **Advanced Color Grading:** Applies one or more `.cube` LUTs sequentially for accurate technical corrections (e.g., V-Log) and creative looks.
- **Robust A/V Synchronization:** The final assembly uses an advanced concatenation method and a sophisticated `amix` audio filter graph to seamlessly blend all audio sources, guaranteeing perfect sync.
- **GPU-First Architecture:** The pipeline is optimized to perform as much work as possible on the GPU (decoding, scaling, encoding) for maximum performance.
- **Powerful Rendering Options:** Includes test mode (`--test`), verbose output (`-v`), partial rendering (`--segments`), source trimming (`--start`, `--end`), and forced re-rendering (`--force-render`).

## Project Structure

Your project folder should be set up like this for the scripts to work correctly:
```.
├── assets/
│   ├── music/        <-- Place your .mp3, .wav, etc. music files here (subfolders are ok)
│   ├── sounds/       <-- Place your .wav or .mp3 sound effects here
│   └── timers/       <-- Generated timer assets will be saved here
├── luts/             <-- Place your .cube LUT files here
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
- **FFmpeg & FFprobe:** Must be installed and accessible in your system's PATH.
- **NVIDIA GPU with CUDA Toolkit installed.**

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Configure Your Style & Audio

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, video resolution, your color grading LUT(s), sound effects, and the new `background_music` options.

### Step 2: Add Audio Assets

1.  Place your sound effect files (e.g., `swoosh.wav`) in the `assets/sounds/` directory.
2.  Place your background music files (e.g., `workout_mix.mp3`) in the `assets/music/` directory. You can create subfolders inside `music/` to organize your library.

### Step 3: Define Your Routine

Open or create a `routine.yaml` file. List each exercise or rest period with its `name` and `length` in seconds.

### Step 4: Generate Timer Assets

The assembly script needs a pre-made timer video for each unique duration in your routine. Run this command for each unique `length` value from your routine file:
```bash
python create_progress_ring.py <duration_in_seconds>
```
**Example:** `python create_progress_ring.py 45`

### Step 5: Assemble the Final Video

The main script has several powerful options for processing your video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> [options]
```

**Example 1: Full Quality Render of an Entire Routine**
The first time you run this, it will encode every segment. If you run it again, it will reuse those segments, making assembly nearly instantaneous.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```

**Example 2: Render a Specific Segment in Test Mode**
This command is perfect for quickly checking the style, overlays, and audio mix for a single part of your video.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test_preview.mp4" --segments 3 --test --verbose
```