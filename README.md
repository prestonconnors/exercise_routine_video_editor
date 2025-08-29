# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays. It uses a series of configuration files and scripts to combine a single long video recording with animated timers and title cards, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **YAML Configuration:** All styling (colors, fonts, sizes, borders) is controlled in a single `config.yaml` file for easy theme changes.
- **Routine Planning:** Video structure is defined in a simple `routine.yaml` file, listing exercises and their durations.
- **Automated Asset Generation:** A script (`create_progress_ring.py`) automatically generates high-quality, reusable animated timer assets.
- **Dynamic Overlays:** The main script (`assemble_video.py`) automatically composites timers and burns in exercise titles for each segment.
- **High Performance:** The timer generation script is optimized to be extremely fast, and the assembly script uses GPU-accelerated FFmpeg commands where possible.
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
└── README.md
```

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

Follow these steps to create your final video.

### Step 1: Configure Your Style

Open `config.yaml` and edit the settings to match your desired visual style. This is where you set fonts, colors, sizes, video resolution, and more. You generally only need to do this once.

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
2.  For each unique duration, run the `create_progress_ring.py` script. The script will automatically read your `config.yaml`, generate the animation, create a `.mov` file, and clean up after itself.

**Example Commands:**
```bash
python create_progress_ring.py 45
python create_progress_ring.py 53
python create_progress_ring.py 60
```
After running these commands, your `assets/timers/` folder will contain `timer_45s.mov`, `timer_53s.mov`, and `timer_60s.mov`.

### Step 4: Assemble the Final Video

Now, run the main assembly script. It requires three arguments: the path to your routine file, the path to your source video footage, and the desired path for the final output video.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video>
```

**Example Command:**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4"
```
The script will now process your video segment by segment and combine everything into the final `final_video.mp4`.