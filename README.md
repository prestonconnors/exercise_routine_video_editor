# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays. It uses a series of configuration files and scripts to combine a single long video recording with animated timers and title cards, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file for easy theme changes.
- **Routine-Based Editing:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets.
- **V-Log / LUT Support:** Automatically applies a specified `.cube` LUT to the source video for professional color grading (e.g., V-Log to Rec.709 conversion), controlled via the config.
- **Configurable Audio:** Automatically convert mono microphone tracks to stereo for better playback compatibility, controlled via the config.
- **Flexible Overlay Positioning:** Place the timer and exercise titles anywhere on the screen using FFmpeg's positioning expressions directly in the config file.
- **Powerful Rendering Options:**
    - **Partial Rendering:** Re-render specific segments of your routine for quick tests.
    - **Source Trimming:** Extract a specific routine from the middle of a long source video using `--start` and `--end` time commands.
- **High Performance:** The timer generation script is highly optimized, and the assembly script uses GPU-accelerated FFmpeg commands where possible.
- **Professional Formats:** Timer assets are created in ProRes 4444 with a transparent alpha channel for high-quality compositing.

## Project Structure

Your project folder should be set up like this for the scripts to work correctly:

```
.
├── assets/
│   └── timers/
│       ├── timer_45s.mov
│       └── timer_53s.mov
├── config.yaml
├── create_progress_ring.py
├── assemble_video.py
├── routine.yaml
├── requirements.txt
└── README.md```

## Setup

### 1. Prerequisites

- **Python 3.8+**
- **FFmpeg:** You must have FFmpeg installed and accessible in your system's PATH. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html). (The full build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) is recommended for Windows users).
- An NVIDIA GPU is recommended to take advantage of `h264_nvenc` encoding for speed. If you don't have one, change the `codec` in `config.yaml` to `libx264`.

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Configure Your Style

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, sizes, video resolution, overlay positions, the path to your color grading LUT, and audio settings. You generally only need to do this once per visual style.

### Step 2: Define Your Routine

Open or create a `routine.yaml` file. List each exercise or rest period with its `name` and `length` in seconds.

**Example `routine.yaml`:**
```yaml
- name: Warmup
  length: 45
- name: Plyo Pushup with Chest Tap
  length: 53
- name: rest
  length: 60
```

### Step 3: Generate Timer Assets

The assembly script needs a pre-made timer video for each unique duration in your routine.

1.  Look at your `routine.yaml` and find all unique `length` values (e.g., 45, 53, 60).
2.  For each unique duration, run the `create_progress_ring.py` script. It will automatically read your `config.yaml`, generate the animation, create a `.mov` file, and clean up after itself.

**Example Commands:**
```bash
python create_progress_ring.py 45
python create_progress_ring.py 53
python create_progress_ring.py 60
```

### Step 4: Assemble the Final Video

The main script has several powerful options for processing your video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> [options]
```

**Options:**
- `--segments "1,3,5"`: Process only specific segments (1-based index).
- `--start 300`: Start using the source video from the 5-minute mark (300 seconds).
- `--end 1800`: Do not use any footage past the 30-minute mark (1800 seconds).

**Example 1: Process the entire routine**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```

**Example 2: Extract a specific routine from the middle of a long recording**
Let's say your actual routine starts 10 minutes into your recording and lasts for 25 minutes.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_cut.mp4" --start 600 --end 2100
```

**Example 3: Test a single segment from the middle of the recording**
This is great for quickly checking your overlay positions and styles.
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test.mp4" --start 600 --segments 4
```
This will process only the 4th exercise in the routine, but it will correctly calculate its start time as `600 + <duration of segments 1, 2, and 3>`.