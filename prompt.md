I need you to act as an expert Python developer and FFmpeg specialist. Your task is to re-create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support a highly detailed structure, including:
- **`paths`:** Directories for asset output.
- **`source_video_processing`:** Controls for color grading, including a `lut_files` key that accepts a list of `.cube` files.
- **`finishing_filters`:** A block for `sharpen`.
- **`progress_ring`:** Settings for the animated timer.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`sound_effects`:** A section to control audio overlays, with a library of effects and rules to trigger them.
- **`video_output`:** Default resolution, encoder, audio settings, `bit_depth`, and advanced NVENC tuning parameters.
- **`test_mode_settings`:** A section that overrides keys from `video_output`.
- **`audio_optimization`:** (New) A dedicated section for final audio mastering, including vocal enhancement (EQ, compression) and EBU R128 loudness normalization targets.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets. Its functionality is stable and does not need to be changed.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags: `--bgm`, `--segments`, `--start`, `--end`, `--test`, `--force-render`, `--verbose`, `--config`.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** Must use `ffprobe` to determine the source pixel format and dynamically select correct pixel formats for processing.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested with an h264 encoder.
3.  **Complex Audio Mixing with Ducking:**
    - Must accept an optional path to a pre-generated background music file via the `--bgm` flag.
    - Must build a multi-input audio filter graph to combine source audio, background music, and triggered sound effects.
    - Must correctly implement audio ducking using the `sidechaincompress` filter to lower the background music volume when a sound effect is active.
    - Must use `amix` to combine all final audio streams into a single track.
4.  **Filter Architecture (GPU-First):** Must perform GPU-native scaling (`scale_cuda`) before downloading the frame for CPU-based filters (`zscale`, `lut3d`, `unsharp`) and overlays (`drawtext`).
5.  **Segment-Level Media Overrides:** Must support `replace_video` and `replace_audio` keys within the `routine.yaml` file for any segment, allowing users to substitute specific video or audio clips (e.g., for custom intros/outros) while maintaining all other processing like overlays and effects.
6.  **Robust Final Assembly:** The concatenation step must copy the video stream but re-encode the audio with `aresample` to guarantee A/V synchronization.
7.  **(New) Two-Stage Audio Mastering:** Must implement a final, two-stage audio optimization process controlled via the config file. This includes (a) vocal enhancement filters (EQ, compression) applied during segment rendering and (b) a two-pass EBU R128 loudness normalization (`loudnorm`) applied to the final concatenated video *without* re-encoding the video stream.

### 4. `create_hook.py` (New Utility)

This utility script automatically creates a short "hook" or "preview" video from a longer source.
- **Purpose:** Identifies and combines the most motion-intensive clips to generate engaging short-form content.
- **Features:**
    - **Routine-Aware Analysis:** Must support a `--routine` flag to parse a `routine.yaml`. When used, it intelligently analyzes only "action" segments (ignoring rests, intros, etc.) for more relevant clip selection.
    - **Variety Prioritization:** When using a routine, the script must prioritize selecting the most active clips from *unique* exercises first before adding duplicates.
    - **Time-Constrained Speed-Up:** Must support a `--max_duration` flag. If the combined clip duration exceeds this value, the final video must be re-encoded and sped up to fit the target time.
    - **Analysis:** Uses FFmpeg's `select='gt(scene,threshold)'` filter for motion scoring and supports optional OpenCL GPU acceleration.
    - **Extraction:** Uses fast, lossless stream copy (`-c copy`) by default. Re-encoding is only triggered if speed changes or transitions are required.
- **Input:** Must accept positional arguments `input`, `num_clips`, `clip_duration`, and optional flags like `--output`, `--threshold`, `--gpu`, `--routine`, and `--max_duration`.

### 5. `download_music_from_youtube_playlists.py`

This is a utility script to acquire high-quality audio.
- **Purpose:** Downloads audio from YouTube URLs (single video or playlist).
- **Strategy:** Employs a quality-first approach:
    - If the best available audio is in AAC/M4A format, it keeps it as-is to avoid transcoding.
    - Otherwise (e.g., Opus/WebM), it performs a single lossless conversion to FLAC.
- **Features:** Must embed metadata and the video thumbnail as cover art into the final audio file (`.m4a` or `.flac`).
- **Dependencies:** Requires `yt-dlp` to be installed and `ffmpeg` to be on the system PATH.
- **Input:** Must accept positional arguments for the output directory and one or more YouTube URLs.

### 6. `create_background_music.py` (New Utility)

This utility pre-generates the entire background audio track for a routine.
- **Purpose:** Analyzes a `routine.yaml` and `config.yaml` to build a single, continuous audio file for the entire video's duration.
- **Features:**
    - **Continuous Playback:** Implements a "radio mix" style where songs play across segments until they finish or a rule forces an interruption.
    - **Rule-Based Playlists:** Supports `file:` rules for specific tracks and `folder:` rules to draw randomly from a themed playlist.
    - **Automatic Crossfading:** Seamlessly crossfades between tracks when a song ends or a rule forces a change, using a `crossfade_duration` setting from the config.
- **Input:** Must accept positional arguments for the routine file and the output audio file.

### 7. Documentation

Provide:
- A `requirements.txt` file listing: PyYAML, Pillow, yt-dlp.
- A comprehensive `README.md` file covering the video generator and all utility scripts.
- The `prompt.md` file itself for project regeneration.

### 8. `run_workflow.py` (Orchestrator)

This is a top-level helper script designed to simplify the entire video creation process by chaining the necessary steps together.
- **Purpose:** To act as a single command-line interface for the most common end-to-end workflow.
- **Process:**
  1.  Parse the specified `routine.yaml` file to identify unique timer lengths and locate the intro video path.
  2.  Execute `create_progress_ring.py` for each unique length to ensure all timer assets exist.
  3.  Execute `create_background_music.py` to generate the complete audio track.
  4.  Execute `create_hook.py` to generate a high-action video. This script *must* use the `routine.yaml` to perform an intelligent, routine-aware analysis.
  5.  Execute `assemble_video.py` with all the generated assets to build the final video.
- **Smart Intro Integration:** The orchestrator must automatically search the parsed routine for a segment named `"intro"`. If that segment contains a `replace_video` key, its path must be used as the `--output` for the `create_hook.py` script. If not found, it should fall back to a default `_hook.mp4` filename.
- **Input:** Must accept positional arguments `routine_file` and `source_video`, along with an optional `--start` flag that is passed directly to *both* `create_hook.py` and `assemble_video.py`.
- **Subprocess Handling:**
  - Must explicitly use the Python executable from the active virtual environment (`sys.executable`) when calling other scripts to prevent `ModuleNotFoundError`.
  - Must ensure that output from child scripts (especially `assemble_video.py`) is streamed to the console in real-time and unbuffered.