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
- **`audio_optimization`:** A dedicated section for final audio mastering, including vocal enhancement (EQ, compression) and EBU R128 loudness normalization targets.
- **`performance`:** A section controlling parallelism. Must include `num_workers` (integer; how many segments to render concurrently across NVENC sessions).

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets. Its functionality is stable and does not need to be changed.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`, and optional flags: `--bgm`, `--segments`, `--start`, `--end`, `--test`, `--force-render`, `--verbose`, `--config`.

**Functional Requirements:**
1.  **Dynamic Bit Depth Pipeline:** Must use `ffprobe` to determine the source pixel format and dynamically select correct pixel formats for processing. The probe result must be cached per-path so repeat calls are free.
2.  **Smart Codec Handling:** Must automatically switch to `hevc_nvenc` if a `bit_depth` of 10 is requested with an h264 encoder.
3.  **Complex Audio Mixing with Ducking:**
    - Must accept an optional path to a pre-generated background music file via the `--bgm` flag.
    - Must build a multi-input audio filter graph to combine source audio, background music, and triggered sound effects.
    - Must correctly implement audio ducking using the `sidechaincompress` filter to lower the background music volume when a sound effect is active.
    - Must use `amix` to combine all final audio streams into a single track.
4.  **Filter Architecture (GPU-First):** Must perform GPU-native scaling (`scale_cuda`) before downloading the frame for CPU-based filters (`zscale`, `lut3d`, `unsharp`) and overlays (`drawtext`). Must NOT pass `-threads 1`/`-filter_threads 0`; let FFmpeg auto-pick threads so the CPU filter graph scales across cores. `lut3d` must use tetrahedral interpolation. Avoid the BT.2020/HLG `zscale` round-trip around the LUT chain (a no-op for V-Log→Rec.709 LUTs); only normalize range to/from full as needed.
5.  **Pre-Baked LUT Chain:** When `source_video_processing.lut_files` contains more than one existing `.cube` file, the pipeline must combine them into a single equivalent cached LUT (under `.cache/luts/`, keyed on input path/mtime/size) by importing `get_or_build_combined_lut` from `combine_luts.py`. The runtime filter graph must then apply exactly one `lut3d` filter.
6.  **Segment-Level Media Overrides:** Must support `replace_video` and `replace_audio` keys within the `routine.yaml` file for any segment, allowing users to substitute specific video or audio clips (e.g., for custom intros/outros) while maintaining all other processing like overlays and effects.
7.  **Parallel Segment Rendering:** Must process segments in two passes:
    - **Pass 1 (sequential, cheap):** Build a list of fully resolved per-segment tasks. All randomness (SFX rule selection, `start_time: 'random'`) must be resolved here using a per-segment seeded RNG (e.g. `random.Random(f"{source}|{i}|{name}")`) so reruns are byte-identical regardless of scheduling order. Each task must include a SHA-256 fingerprint covering every input that affects the rendered bytes (trim window, source mtime, replacement clips + mtimes, timer file, BGM path/offset/mtime, SFX rule + computed delay, codec/quality settings, LUT chain, audio optimization config).
    - **Pass 2 (parallel):** Render missing segments via `concurrent.futures.ThreadPoolExecutor(max_workers=performance.num_workers)`. Each worker must collect its log lines and emit them as a contiguous block on completion so per-segment logs stay grouped. The number of workers must be capped to the number of pending tasks.
8.  **Manifest-Based Reuse Cache:** Must persist a JSON manifest at `.cache/segments_manifest.json` mapping `temp_segment_<i>.mp4` → fingerprint. On startup, segments whose temp file exists, is non-empty, and matches the fingerprint must be reused without invoking `ffprobe`. Pre-existing temps with no manifest entry must fall back to a one-time `ffprobe` validity check (`is_video_file_valid`) and then be fingerprinted into the manifest. `--force-render` must bypass the manifest entirely.
9.  **Robust Final Assembly:** Concatenation must be a lossless stream copy of *both* video and audio (`-c copy`). Audio re-encoding only happens later in the loudness normalization pass.
10. **NVENC Tuning:** When the codec is `h264_nvenc`/`hevc_nvenc`, the encoder must use `-rc-lookahead 20 -spatial_aq 1 -temporal_aq 1 -aq-strength 8 -rc vbr -tune hq -multipass qres -bf 3` (note: `qres`, not `fullres` — visually indistinguishable but ~1.5× faster). For `hevc_nvenc`, set `-profile:v main10` for 10-bit, otherwise `main`.
11. **Two-Stage Audio Mastering:** Must implement a final, two-stage audio optimization process controlled via the config file. This includes (a) vocal enhancement filters (EQ, compression) applied during segment rendering and (b) a two-pass EBU R128 loudness normalization (`loudnorm`) applied to the final concatenated video *without* re-encoding the video stream.
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
    - **Flexible Rule Exit Behavior:** The system needs to handle the transition out of a rule-driven segment with more nuance.
- **Input:** Must accept positional arguments for the routine file and the output audio file.

### 7. Documentation

Provide:
- A `requirements.txt` file listing: PyYAML, Pillow, yt-dlp, mutagen, numpy.
- A comprehensive `README.md` file covering the video generator and all utility scripts, including a Performance & Caching section.
- The `prompt.md` file itself for project regeneration.

### 7a. `combine_luts.py` (LUT Pre-Bake Utility)

A standalone utility that pre-bakes a chain of `.cube` 3D LUTs into a single equivalent `.cube` LUT, callable both as a CLI and as a library.
- **API:** Must export `get_or_build_combined_lut(lut_paths, cache_dir='.cache/luts', output_size=None) -> str`. The function returns the path to a cached combined LUT, building it on cache miss. Cache key must be a stable hash over each input LUT's absolute path, mtime, and size (and the requested output grid size, if any).
- **CLI:** `python combine_luts.py <lut1.cube> <lut2.cube> [...] --output <out.cube> [--size N]`.
- **Math:** Must parse `LUT_3D_SIZE`, `DOMAIN_MIN`, `DOMAIN_MAX`, and the sample list; apply LUTs in order via trilinear interpolation; default the output grid size to the maximum of the input grid sizes.
- **Dependencies:** `numpy` only (no OpenColorIO/Pillow requirement).

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