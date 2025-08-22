You are an expert Python developer specializing in robust, configurable video automation scripts.

Your task is to write a single, complete, self-contained Python script named `exercise_routine_video_editor.py` that automates the creation of workout videos. The script must be a command-line tool that takes a raw video file and a workout routine defined in a YAML file, and produces a final video with dynamic, professional overlays. The entire visual style of the overlays must be configurable via a separate YAML file.

### Core Libraries
-   `moviepy` for all video manipulation.
-   `PyYAML` to parse the input YAML files.
-   `Pillow` (PIL) for all dynamic frame generation (countdown timer, progress bar, and exercise name background) to ensure performance and reliability.
-   `argparse` for command-line argument parsing.
-   `numpy` for frame manipulation.
-   `os` for detecting CPU count.
-   `random` for color generation.

### Input Files

1.  **Workout Routine YAML**: A list of dictionaries, each with a `name`, `length` (in seconds), and optional `type` (e.g., 'warmup', 'rest').
2.  **Visual Configuration YAML (`config.yaml`)**: A dictionary defining the entire visual style. It must contain the following sections and keys:
    -   `safe_margins`: `horizontal_percent` and `vertical_percent` to keep elements away from screen edges.
    -   `font_file`, `font_color`, `stroke_color`: Global defaults.
    -   `exercise_name`: `position`, `font_size`, `stroke_width`, and `background_padding_percent`. It can override `font_file`.
    -   `countdown_timer`: `position`, `font_size`, `stroke_width`, `background_padding_percent`, and a `progress_circle` with a `width`. It can override `font_file`.
    -   `progress_bar`: `position`, `height`, `foreground_color`, and `background_color`.
    -   `next_up_preview`: `position`, `show_before_end_seconds`, `scale`, and a `text` subsection with `font_size`, `stroke_width`, and an optional `font_file`.

### Script Functionality

1.  **Command-Line Interface:** The script must use `argparse` to accept the following arguments:
    -   `-y, --yaml`: Required path to the workout routine YAML.
    -   `-i, --input`: Required path to the input raw video file.
    -   `-o, --output`: Required path for the final output video.
    -   `-c, --config`: Optional path to the visual config YAML (defaults to `config.yaml`).
    -   `-t, --test`: Optional flag (`action='store_true'`) for a fast, low-quality, silent, 480p, 15fps render.
    -   `--gpu`: Optional flag (`action='store_true'`) to attempt GPU-accelerated encoding.

2.  **Overlay Logic:**
    -   **Safe Margins:** Implement a helper function `calculate_safe_position` that takes an asset's size and position strings (e.g., `['left', 'top']`) and returns the correct `(x, y)` coordinate based on the `safe_margins` from the config file.
    -   **Exercise Name:**
        -   For each exercise, generate a new random, semi-transparent background color.
        -   **Crucially, use Pillow to accurately measure the text's true bounding box.**
        -   Create a background box whose size is based on the text's measured size plus the `background_padding_percent`.
        -   Use Pillow to draw the background and the perfectly centered text onto a canvas.
        -   Convert this canvas to a MoviePy `ImageClip` and position it using the safe margin function.
    -   **Countdown Timer:**
        -   This must be a **perfect circle**. The size of the circle should be a square whose side is based on the longest dimension of the text "00" plus the `background_padding_percent`.
        -   For each exercise, generate two different random colors: one for the semi-transparent background circle and one for the fully opaque progress arc.
        -   The background must be a semi-transparent colored circle.
        -   It must have a depleting circular progress bar around its border that drains **counter-clockwise**.
        -   The countdown number must be perfectly centered (horizontally and vertically) within the circle.
        -   **This entire element must be drawn using Pillow on every frame** to ensure perfect alignment and bypass MoviePy's `TextClip` bugs.
    -   **Progress Bar:** This should track the total duration of only the main workout exercises (not warmup, rest, etc.). It should be drawn efficiently using Pillow.
    -   **Next Up Preview**: A scaled-down subclip of the next exercise that fades in and out during the final seconds of the current exercise. The fade effect must be implemented reliably using a custom mask.

3.  **Performance:**
    -   The script must automatically use all available CPU cores (`os.cpu_count()`) for encoding.
    -   The `--gpu` flag should make the script attempt to use the `h264_nvenc` codec. It must use different `preset` values for GPU (`p1`, `p4`) vs. CPU (`ultrafast`, `medium`) and handle potential rendering errors by falling back to the CPU.

4.  **Code Quality:**
    -   The script must be well-commented and organized into logical functions.
    -   All file and resource handling should be robust (e.g., check if files exist, close video clips).
    -   It must be contained within a single Python file with a `if __name__ == "__main__":` block.