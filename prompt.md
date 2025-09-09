I need you to act as an expert Python developer and FFmpeg specialist. Your task is to create a complete, automated pipeline for generating styled exercise videos based on a pre-existing, functional set of Python scripts and a YAML configuration file.

The project consists of two main Python scripts, a central `config.yaml` file, and supporting documentation. You must adhere to the final, stable architecture provided.

### 1. `config.yaml`

The configuration file must support the following structure:
- **`paths`:** Directories for asset output.
- **`opencl`**: A key for the OpenCL device string (e.g., "0.0").
- **`source_video_processing`:** Controls for color grading (`apply_lut` and `lut_file` path).
- **`finishing_filters`:** Blocks for `denoise` and `sharpen`, each with an `enabled` flag and strength/amount. The `denoise` block must support a `backend` key ('opencl' or 'cpu').
- **`progress_ring`:** Settings for the animated timer.
- **`text_overlays.exercise_name`:** Settings for the exercise name titles.
- **`video_output`:** Default resolution, codec, and audio settings, plus a `framing_method` key ('crop' or 'scale'). This section must also support advanced NVENC tuning parameters like `rc-lookahead`, `spatial_aq`, `multipass`, etc.
- **`test_mode_settings`:** A section that overrides keys from `video_output` for fast previews.

### 2. `create_progress_ring.py`

This script generates reusable animated timer assets.
- **Input:** Must take a single command-line argument: `duration` (in seconds).
- **Functionality:** It must generate a PNG sequence using Pillow, compile it into a `prores_aw` video with FFmpeg, and delete the temporary frames.
- **Performance:** The frame generation loop must use an efficient "incremental drawing" method.

### 3. `assemble_video.py`

This is the main orchestration script that builds the final video.
- **Input:** Must accept positional arguments: `routine.yaml`, `source_video`, `output_video`.
- **Optional Arguments:** Must accept optional flags: `--segments`, `--start`, `--end`, `--test`, and `--verbose`.

**Functional Requirements:**
1.  **Read Inputs:** Parse the `routine.yaml` and `config.yaml`.
2.  **FFmpeg Command Generation:**
    - The command must start with hardware acceleration (`-hwaccel cuda -hwaccel_output_format cuda`) and threading optimizations.
    - If OpenCL is enabled in the config, the command **must** include `-init_hw_device` and `-filter_hw_device` before the `-ss` input argument.
    - Input trimming must be done with `-ss` and `-to` before `-i`.
3.  **Filter Architecture (CRITICAL):**
    - The filter chain **must** follow a "GPU-first, then CPU" logic.
    - **Chain 1:** Start with the source `[0:v]` and immediately scale on the GPU using `scale_cuda` with `force_original_aspect_ratio=increase`. Name this stream `[gpu_scaled]`.
    - **Chain 2:** Take `[gpu_scaled]` as input, download it (`hwdownload`), reset timestamps (`setpts`), and perform all CPU-bound operations in sequence: `crop` (with even-aligned offsets), the `zscale/lut3d/zscale` color pipeline, and the CPU `unsharp` filter. Name this `[cpu_processed]`.
    - **Chain 3 (Optional):** If OpenCL denoising is enabled, take `[cpu_processed]` as input, `hwupload` it, run `nlmeans_opencl`, and `hwdownload` the result back. Name this `[ocl_done]`.
    - **Chain 4:** Take the last processed stream as input and perform a CPU-based `overlay` for the timer asset.
    - **Chain 5:** Take the result of the overlay and perform a final CPU-based `drawtext` for the exercise name.
4.  **Final Assembly:** If one segment is created, rename the temp file. If multiple, concatenate them.
5.  **Cleanup & Feedback:** The script must delete temporary files and provide verbose feedback and timing metrics.

### 4. Documentation

Provide:
- A `requirements.txt` file listing `PyYAML` and `Pillow`.
- A `README.md` file explaining the project's purpose, setup, and a detailed workflow.
- The `prompt.md` file itself.