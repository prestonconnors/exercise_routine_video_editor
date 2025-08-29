import os
import sys
import yaml
import textwrap
import subprocess
from pathlib import Path  # Import the modern path handling library

def sanitize_text_for_ffmpeg(text: str) -> str:
    """
    Escapes characters that are special to FFmpeg's drawtext filter.
    Most importantly, it handles single quotes and colons.
    """
    text = text.replace('\\', '\\\\')
    text = text.replace("'", "'\\\\\\''")
    text = text.replace('"', '\\"')
    text = text.replace('%', '\\%')
    text = text.replace(':', '\\:')
    return text

def prepare_text_for_ffmpeg(text: str, line_width: int = 25) -> str:
    """
    Wraps text to a given line width and sanitizes it to be safely 
    injected into an FFmpeg drawtext filter string.
    """
    wrapped_lines = textwrap.wrap(text, width=line_width, break_long_words=True, replace_whitespace=True)
    wrapped_text = "\n".join(wrapped_lines)
    return sanitize_text_for_ffmpeg(wrapped_text)

def assemble_video(config_path: str, routine_path: str, source_video_path: str, output_path: str):
    """
    Assembles the final exercise video based on a routine and a config file.
    """
    # --- Load Configurations ---
    try:
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FATAL: Main config file not found at '{config_path}'")
        sys.exit(1)
        
    try:
        with open(routine_path, 'r') as f:
            routine = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FATAL: Routine file not found at '{routine_path}'")
        sys.exit(1)

    if not os.path.exists(source_video_path):
        print(f"FATAL: Source video not found at '{source_video_path}'")
        sys.exit(1)

    # Store config sections in easy-to-use variables
    paths_cfg = cfg['paths']
    video_cfg = cfg['video_output']
    title_cfg = cfg['text_overlays']['exercise_name']
    ring_cfg = cfg['progress_ring']

    current_timestamp = 0.0
    segment_files = []

    print("--- 🏋️ Starting Video Assembly 🏋️ ---")

    # --- Loop through each exercise in the routine ---
    for i, exercise in enumerate(routine):
        name = exercise.get('name', 'Unnamed Exercise')
        length = float(exercise.get('length', 0))

        if length <= 0:
            print(f"  > WARNING: Skipping segment '{name}' because its length is {length}.")
            continue
        
        start_time = current_timestamp
        end_time = current_timestamp + length
        
        output_segment_file = f"temp_segment_{i}.mp4"
        print(f"\nProcessing Segment {i+1}/{len(routine)}: '{name}' ({length}s)")

        # Check for Required Timer Asset
        timer_duration = int(length)
        timer_file = os.path.join(paths_cfg['asset_output_dir'], paths_cfg['timers_subdir'], f'timer_{timer_duration}s.mov')

        use_timer = os.path.exists(timer_file)
        if not use_timer:
            print(f"  > WARNING: Timer file not found: '{timer_file}'.")
            print(f"  > Please generate it first by running: python create_progress_ring.py {timer_duration}")

        # --- Build the -filter_complex FFmpeg String ---
        
        filter_complex = (
            f"[0:v]trim=start={start_time}:end={end_time},setpts=PTS-STARTPTS,"
            f"scale={video_cfg['resolution']},setsar=1[base];"
        )
        
        last_stream = "[base]"

        if use_timer:
            filter_complex += f"[1:v]scale={ring_cfg['size']}:-1[timer];"
            filter_complex += f"{last_stream}[timer]overlay=x=(W-w)/2:y=50[v_with_timer];"
            last_stream = "[v_with_timer]"

        clean_text = prepare_text_for_ffmpeg(name, title_cfg['wrap_at_char'])
        show_from = title_cfg['show_from_second']
        show_to = show_from + title_cfg['show_for_seconds']
        font_path_for_ffmpeg = title_cfg['font_file'].replace('\\', '/').replace(':', '\\:')

        filter_complex += (
            f"{last_stream}drawtext="
            f"fontfile='{font_path_for_ffmpeg}':"
            f"text='{clean_text}':"
            f"fontsize={title_cfg['font_size']}:"
            f"fontcolor={title_cfg['font_color']}:"
            f"box=1:boxcolor={title_cfg['box_color']}:boxborderw={title_cfg['box_border_width']}:"
            f"x={title_cfg['position_x']}:"
            f"y={title_cfg['position_y']}:"
            f"enable='between(t,{show_from},{show_to})'[final_v]"
        )

        # --- Build and Run the FFmpeg Command ---
        ffmpeg_cmd = ['ffmpeg', '-y', '-i', source_video_path]
        if use_timer:
            ffmpeg_cmd.extend(['-i', timer_file])
        
        ffmpeg_cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[final_v]',
            '-map', '0:a?',
            '-c:v', video_cfg['codec'], '-preset', video_cfg['preset'], '-cq', str(video_cfg['quality']),
            '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate'],
            output_segment_file
        ])
        
        try:
            result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            print(f"  > Successfully created segment: {output_segment_file}")
            segment_files.append(output_segment_file)
        except subprocess.CalledProcessError as e:
            print(f"\n--- FATAL: FFmpeg failed while creating segment for '{name}'. ---")
            e.cmd[e.cmd.index('-filter_complex') + 1] = f'"{e.cmd[e.cmd.index("-filter_complex") + 1]}"'
            print("  > Failing command (for copy/pasting into shell):\n", " ".join(e.cmd))
            print("\n  > FFmpeg error output (stderr):\n", e.stderr)
            sys.exit(1)

        current_timestamp = end_time

    # --- Concatenate all segments ---
    if not segment_files:
        print("\nNo segments were created. Aborting final assembly.")
        sys.exit(1)

    print("\n--- 🎞️ Concatenating Segments ---")
    concat_file = "concat_list.txt"
    with open(concat_file, 'w', encoding='utf-8') as f:
        for file in segment_files:
            # --- MODIFIED: Use pathlib to create a clean, forward-slash path ---
            # This is robust and avoids the f-string backslash syntax error.
            path_obj = Path(file).resolve()
            clean_path = path_obj.as_posix()
            f.write(f"file '{clean_path}'\n")

    concat_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', output_path]
    try:
        subprocess.run(concat_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        print(f"  > FATAL: FFmpeg failed while concatenating segments.")
        print("  > Failing command:", " ".join(e.cmd))
        print("  > FFmpeg error output (stderr):", e.stderr)
        sys.exit(1)

    # --- Clean up temporary files ---
    print("\n--- 🧹 Cleaning Up Temporary Files ---")
    try:
        os.remove(concat_file)
        for file in segment_files:
            os.remove(file)
    except OSError as e:
        print(f"  Warning: Could not delete all temporary files: {e}")
        
    print(f"\n✅ Video assembly complete! Final video saved to: {output_path}")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Creates a complete exercise video from a source file and a routine plan.")
        print("\nUsage: python assemble_video.py <routine.yaml> <source_video.mov> <output_video.mp4>")
        print("\nExample: python assemble_video.py my_workout.yaml D:/workouts/raw_footage.mov final_workout.mp4")
        sys.exit(1)
    
    config_file_path = 'config.yaml'
    routine_file_path = sys.argv[1]
    source_video_file_path = sys.argv[2]
    output_video_file_path = sys.argv[3]

    assemble_video(config_file_path, routine_file_path, source_video_file_path, output_video_file_path)