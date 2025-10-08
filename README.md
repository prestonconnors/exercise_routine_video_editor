# Automated Exercise Video Generator

This project is a Python-based pipeline for automatically creating styled exercise videos with dynamic overlays, sound effects, and background music. It uses a series of configuration files and scripts to combine a single long video recording with animated timers, title cards, and rule-based audio cues, producing a final, edited video ready for platforms like YouTube.

The entire workflow is driven by FFmpeg, orchestrated by Python, and styled via a central `config.yaml` file, making it incredibly flexible and efficient.

## Features

- **Centralized Styling:** All visual elements (colors, fonts, sizes, positions) are controlled in a single `config.yaml` file.
- **Efficient Re-rendering:** The pipeline automatically detects and reuses previously rendered video segments, only encoding new or changed portions.
- **Rule-Based Sound Effects:** Define a library of sound effects and create rules to automatically play sounds based on keywords in the exercise name.
- **Segment Media Overrides:** Easily replace the video and/or audio for any specific segment (like an intro or outro) directly within your `routine.yaml`.
- **(New) Final Audio Mastering:** An automated, two-stage process produces professional, platform-ready audio. First, it applies vocal enhancement (EQ for clarity, compression for consistency) during segment rendering. Then, after the video is assembled, it performs a final EBU R128 loudness normalization pass to meet YouTube/Instagram standards, all without re-encoding the video.
- **Dynamic Background Music:**
  - Creates a continuous "radio mix" style track that plays across segments.
  - A song continues playing until it ends naturally or a rule forces an interruption.
  - Supports rule-based playlists by using a `folder:` key to draw random tracks from a specific directory for certain exercises.
  - **Smooth Transitions:** Automatically crossfades between tracks when a rule forces a song change.
  - **Audio Ducking:** Professional-grade feature that automatically lowers the music volume when a sound effect plays, ensuring clarity.
  - **Global Fade:** Apply an automated fade-in and fade-out at the end of the final video for a polished finish.
- **Automated Asset Generation:** The `create_progress_ring.py` script automatically generates high-quality, reusable animated timer assets.
- **Professional 10-Bit HDR Workflow:** Preserves color fidelity from source to output using a 10-bit pipeline and sequential `.cube` LUT application.
- **Robust A/V Synchronization:** Guarantees perfect sync by re-encoding the final audio track with a sophisticated `amix` filter graph.
- **GPU-First Architecture:** The pipeline is optimized to use the GPU (CUDA/NVENC) for decoding, scaling, and encoding for maximum performance.
- **Powerful Rendering Options:** Includes test mode (`--test`), partial rendering (`--segments`), source trimming (`--start`, `--end`), and forced re-rendering (`--force-render`).

## Utility Scripts

This project includes powerful standalone scripts to prepare assets and create promotional content.

### Continuous Background Music Creator (New)

The `create_background_music.py` script is a powerful utility that pre-generates the entire background music track for your routine. It analyzes your routine file and `config.yaml` to build a single, continuous audio file with smooth transitions.

- **"Radio Mix" Style Playback:** A song will play across multiple exercise segments until it ends, then a new random song will be chosen.
- **Rule-Based Playlists:** Use a `folder:` key in your `background_music` rules to create themed playlists (e.g., "high-energy," "cool-down") that automatically trigger for specific exercises.
- **Automatic Crossfading:** When a rule forces a song to change, the script automatically generates a smooth crossfade between the outgoing and incoming tracks.

**Usage:**
```bash
python create_background_music.py <routine_yaml_path> <output_audio_file>
```
**Example:**
```bash
# Generate the full music track for the Monday routine
python create_background_music.py "routine.yaml" "background_music.m4a"
```

### Action Hook Video Creator

The `create_hook.py` script automatically finds the most motion-intensive scenes in your long video and combines them into a short, high-action preview video. This is perfect for creating social media "hooks."

- **Intelligent Scene Detection:** Analyzes the video to find segments with the most motion. Supports optional GPU (OpenCL) acceleration for faster analysis.
- **Targeted Analysis:** Use the `--center_focus` flag to analyze only the center of the frame, ignoring background movement and dramatically improving accuracy for subject-focused videos.
- **Blazing-Fast & Lossless:** Uses FFmpeg stream copy to extract clips without re-encoding, preserving quality and making the process extremely fast.
- **Highly Customizable:** Control the number of clips, the length of each clip, and the motion detection sensitivity.

**Usage:**
```bash
python create_hook.py <source_video> <num_clips> <clip_duration_sec> [options]
```
**Example:**
```bash
# Find the 5 most active 1-second clips, focusing on the center 60% of the video.
python create_hook.py "final_video.mp4" 5 1 -o "hook.mp4" --gpu --scoring peak --center_focus 0.6
```

### Quality-First Music Downloader

Included is `download_music_from_youtube_playlists.py`, a powerful script for downloading high-quality audio tracks for your projects.

- **Smart Format Selection:** It downloads the best possible audio, keeping the original M4A/AAC file if available to avoid re-encoding. Other formats are converted losslessly to FLAC.
- **Metadata and Cover Art:** Automatically embeds metadata and thumbnail art into the downloaded files.
- **Playlist & Video Support:** Works with both single video URLs and entire playlists.

**Usage:**
```bash
python download_music_from_youtube_playlists.py "<output_folder>" <youtube_url_or_playlist>
```
**Example:**
```bash
# Download a playlist into the project's music folder
python download_music_from_youtube_playlists.py "assets/music" "https://www.youtube.com/playlist?list=PLw-VjHDlSEoA0L_k1gH-2wcy_vj7s4k5-"
```

## Project Structure

Your project folder should be set up like this for the scripts to work correctly:
```.
├── assets/
│   ├── music/        <-- Place your .mp3, .flac, .m4a files here (subfolders are ok)
│   ├── sounds/       <-- Place your .wav or .mp3 sound effects here
│   └── timers/       <-- Generated timer assets will be saved here
├── luts/             <-- Place your .cube LUT files here
├── config.yaml
├── routine.yaml
├── assemble_video.py
├── create_hook.py
├── create_progress_ring.py
├── create_background_music.py
├── download_music_from_youtube_playlists.py
├── requirements.txt
└── README.md
```

## Setup

### 1. Prerequisites

- **Python 3.8+**
- **FFmpeg & FFprobe:** Must be installed and accessible in your system's PATH.
- **NVIDIA GPU with CUDA Toolkit installed** (for `assemble_video.py`). An OpenCL-compatible GPU can be used for `create_hook.py`.

### 2. Install Python Dependencies

In your terminal, navigate to the project folder and run:
```bash
pip install -r requirements.txt
```

## Workflow: How to Create a Video

### Step 1: Download Background Music (Optional)

Use the included downloader to populate your music library. You can create subfolders for different genres (e.g., `assets/music/high-energy`, `assets/music/calm`).
```bash
python download_music_from_youtube_playlists.py "assets/music" <youtube_url>
```

### Step 2: Configure Your Style & Audio

Open `config.yaml` and edit the settings. This is where you set everything: fonts, colors, video resolution, your color grading LUT(s), sound effects, `background_music` rules, and the new `audio_optimization` settings.

### Step 3: Add Audio Assets

1.  Place your sound effect files (e.g., `swoosh.wav`) in the `assets/sounds/` directory.
2.  Ensure your background music files are organized in the `assets/music/` directory.

### Step 4: Define Your Routine

Open or create a `routine.yaml` file. List each exercise or rest period with its `name` and `length` in seconds.

You can also override the video or audio for a specific segment using the `replace_video` and `replace_audio` keys. This is perfect for adding custom, pre-edited intros or outros.

**Example `routine.yaml` with Overrides:**
```yaml
- name: "Intro"
  length: 10
  # This segment's video is replaced by your premade intro.
  # The audio still comes from the main source video, as requested.
  replace_video: 'C:/assets/my_premade_intro.mov'

- name: "Burpees"
  length: 45
  # This is a normal segment using the main source video.
```

### Step 5: Generate Timer Assets

The assembly script needs a pre-made timer video for each unique duration in your routine. Run this command for each unique `length` value from your routine file:
```bash
python create_progress_ring.py <duration_in_seconds>
```
**Example:** `python create_progress_ring.py 45`

### Step 6: Generate the Background Music Track

Run the new script to create a single audio file for the entire routine.
```bash
python create_background_music.py routine.yaml background_music.m4a
```

### Step 7: Assemble the Final Video

The main script now accepts the background music file as a new argument, `--bgm`. After the video segments are concatenated, the script will automatically run the final audio optimization pass if it's enabled in your `config.yaml`.

**Command Structure:**
```bash
python assemble_video.py <routine_file> <source_video> <output_video> --bgm <music_file> [options]
```

**Example 1: Full Quality Render with Music**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "final_video.mp4" --bgm "background_music.m4a"
```

**Example 2: Test a Single Segment with Music**
```bash
python assemble_video.py routine.yaml "D:/Video/raw_workout.MOV" "test_preview.mp4" --bgm "background_music.m4a" --segments 3 --test -v
```

## Automated Workflow Script (Recommended)

To simplify the video creation process, you can use the provided `run_workflow.py` script. This script automatically performs Steps 5, 6, and 7 in a single command, making it the most efficient way to generate a complete video. It reads your routine file to determine which timers to create before generating the music and assembling the final video.

- **Purpose:** Automates timer generation, background music creation, and final video assembly.
- **Features:**
    - Intelligently parses your `routine.yaml` to create only the required timer assets.
    - Provides real-time progress output during the video assembly stage.
    - Passes through key options like `--start` to trim the source video.

**Usage:**
```bash
# General structure
python run_workflow.py <routine_yaml_path> <source_video_path> [options]

# Example: Create the Monday video, trimming the first 30 seconds of the source footage
python run_workflow.py "routine.yaml" "D:/Video/raw_workout.MOV" --start 30
```