import subprocess
import os
import argparse
import sys
import operator
import tempfile
import shlex
import json

def get_video_pix_fmt(input_file):
    """
    Uses ffprobe to get the pixel format of the first video stream.
    """
    print("[INFO] Detecting video pixel format...")
    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        input_file
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video_stream = next((stream for stream in data['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream and 'pix_fmt' in video_stream:
            pix_fmt = video_stream['pix_fmt']
            print(f"[SUCCESS] Detected pixel format: {pix_fmt}")
            return pix_fmt
        else:
            print("[WARNING] Could not determine pixel format. Defaulting to 'yuv420p'.")
            return 'yuv420p' # A safe default
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[WARNING] ffprobe failed to run or parse output: {e}. Defaulting to 'yuv420p'.")
        return 'yuv420p' # A safe default

def check_ffmpeg():
    """Checks if FFmpeg is installed and in the system's PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("FFmpeg found.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: FFmpeg is not installed or not in your system's PATH.")
        return False

def analyze_video(input_file, threshold, use_gpu=False, cl_device="0.0", start_time=0.0, end_time=None, center_focus=None):
    """
    Analyzes the video file, optionally cropping to the center for motion detection.
    """
    print(f"\n--- PHASE 1: ANALYZING VIDEO FOR MOTION ---")
    if start_time > 0.0 or end_time is not None:
        end_str = f" to {end_time}s" if end_time is not None else " until the end"
        print(f"Analyzing source video from {start_time}s{end_str}")

    crop_filter_str = ""
    if center_focus:
        if 0.1 <= center_focus <= 1.0:
            print(f"[INFO] Focusing analysis on the center {center_focus*100:.0f}% of the frame.")
            # Format is crop=width:height:x:y. We use FFmpeg's input width/height variables.
            crop_filter_str = f"crop=w=iw*{center_focus}:h=ih*{center_focus},"
        else:
            print(f"[WARNING] Invalid --center_focus value '{center_focus}'. It must be between 0.1 and 1.0. Ignoring.")


    if use_gpu:
        print(f"Using GPU acceleration for analysis (OpenCL on device {cl_device})")
        source_pix_fmt = get_video_pix_fmt(input_file)
        hwdownload_format = source_pix_fmt

        if hwdownload_format == 'yuv420p10le':
            hwdownload_format = 'p010le'
            print(f"[INFO] Adjusted pixel format to '{hwdownload_format}' for hwdownload compatibility.")

        print(f"[INFO] Using format '{hwdownload_format}' for GPU->CPU transfer.")
    else:
        print(f"Using CPU for analysis")

    log_filename = "scene_scores_temp.log"
    command = ["ffmpeg", "-y"]

    if start_time > 0.0:
        command.extend(["-ss", str(start_time)])
    if use_gpu:
        command.extend(["-init_hw_device", f"opencl=ocl:{cl_device}"])
    if start_time > 0.0 and end_time is not None:
        command.extend(["-copyts"])
    command.extend(["-i", input_file])
    if end_time is not None:
        if end_time <= start_time:
            print("[ERROR] End time must be greater than start time.")
            return False
        command.extend(["-to", str(end_time)])

    if use_gpu:
        filter_chain = (
            f"hwupload,"
            f"hwdownload,format={hwdownload_format},"
            f"{crop_filter_str}" # Crop is a CPU filter, so it goes after hwdownload
            f"scale=w=320:h=240,"
            f"fps=15,select='gt(scene,{threshold})',metadata=print:file={log_filename}"
        )
        command.extend(["-filter_hw_device", "ocl", "-vf", filter_chain])
    else:
        # Standard CPU-only filter chain
        filter_chain = f"{crop_filter_str}scale=w=320:h=240,fps=15,select='gt(scene,{threshold})',metadata=print:file={log_filename}"
        command.extend(["-vf", filter_chain])

    command.extend(["-f", "null", "-"])
    try:
        print("\n[INFO] Starting FFmpeg scene analysis. See live progress below:")
        print("----------------------------------------------------------------------")
        # The 'stderr=subprocess.PIPE' argument has been removed to allow live output.
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        print("\n----------------------------------------------------------------------")
        print("[SUCCESS] FFmpeg analysis complete.")
        return True
    except subprocess.CalledProcessError as e:
        # Since stderr was not captured, it has already been printed to the screen.
        # We now print a simpler error message.
        full_command_str = ' '.join(shlex.quote(c) for c in command)
        print(f"\n[ERROR] FFmpeg analysis failed. See the error message above.")
        print(f"Full Command: {full_command_str}")
        return False
    except KeyboardInterrupt:
        print("\n\n[INFO] Process cancelled by user.")
        return False

def find_most_active_clips(log_file, clip_duration_sec, num_clips, scoring_method='sum'):
    """
    Parses a two-line log format to find the start times of the most active clips.
    """
    print("\n--- PHASE 2: PARSING RESULTS ---")
    print(f"Finding the most active scenes from the analysis log using '{scoring_method}' scoring...")
    scene_scores = {}
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            i = 0
            while i < len(lines) - 1:
                current_line, next_line = lines[i], lines[i+1]
                if "pts_time:" in current_line and "lavfi.scene_score=" in next_line:
                    try:
                        time_str = [p for p in current_line.strip().split() if p.startswith("pts_time:")][0]
                        timestamp = float(time_str.split(':')[1])
                        score = float(next_line.strip().split('=')[1])
                        interval_start = int(timestamp / clip_duration_sec) * clip_duration_sec
                        if scoring_method == 'peak':
                            current_peak = scene_scores.get(interval_start, 0)
                            scene_scores[interval_start] = max(current_peak, score)
                        else: # The default 'sum' method
                            current_sum = scene_scores.get(interval_start, 0)
                            scene_scores[interval_start] = current_sum + score
                        i += 2
                    except (ValueError, IndexError): i += 1
                else: i += 1
    except FileNotFoundError:
        print(f"Error: Log file '{log_file}' not found. Analysis likely failed.")
        return []

    if not scene_scores:
        print("[WARNING] Could not detect any motion with the current threshold.")
        print("          Try running again with a more sensitive (lower) --threshold value.")
        return []
    sorted_clips = sorted(scene_scores.items(), key=operator.itemgetter(1), reverse=True)
    print(f"[SUCCESS] Found {len(sorted_clips)} potential time windows. Selecting the top {num_clips}.")
    return sorted([clip[0] for clip in sorted_clips[:num_clips]])

def extract_and_combine(input_file, start_times, clip_duration, output_file):
    print("\n--- PHASE 3: EXTRACTING & COMBINING CLIPS (No Re-encoding)---")
    print("Using stream copy for fast video extraction. This process is very fast and does not use the GPU for encoding.")
    with tempfile.TemporaryDirectory() as tempdir:
        file_list_path = os.path.join(tempdir, "files.txt")
        temp_files_for_concat = []
        for i, start_time in enumerate(start_times):
            temp_filename = os.path.join(tempdir, f"temp_clip_{i+1}.mp4")
            print(f"\n[INFO] Extracting clip {i+1} of {len(start_times)} (starts at {start_time:.2f}s)...")
            command_extract = ["ffmpeg", "-y", "-ss", str(start_time), "-i", input_file, "-t", str(clip_duration), "-c", "copy", "-an", temp_filename]
            try:
                subprocess.run(command_extract, check=True, capture_output=True)
                print(f"[SUCCESS] Clip {i+1} extracted.")
                temp_files_for_concat.append(temp_filename)
            except subprocess.CalledProcessError as e:
                error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg error."
                print(f"\n[ERROR] Failed to extract clip at {start_time:.2f}s:\n{error_message}")

        if not temp_files_for_concat:
            print("[ERROR] No clips were successfully extracted. Final video cannot be created.")
            return False
        with open(file_list_path, "w") as f:
            for temp_file in temp_files_for_concat:
                f.write(f"file '{temp_file.replace(os.sep, '/')}'\n")
        print("\n[INFO] Stitching final video...")
        concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_path, "-c", "copy", output_file]
        try:
            subprocess.run(concat_cmd, check=True, capture_output=True)
            print("[SUCCESS] Final video stitched.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg concat error."
            print(f"[ERROR] Failed to combine clips.\n{error_message}")
            return False
    print(f"\n-------------------------------------------------\n         PROCESS COMPLETE\nYour hook video has been saved as: {output_file}\n-------------------------------------------------")
    return True

def extract_and_fade_combine(input_file, start_times, clip_duration, output_file, fade_duration=0.25, encoder="libx264", cuda_device="0"):
    gpu_encoders = ['h264_nvenc', 'hevc_nvenc', 'h264_amf', 'hevc_amf', 'h264_videotoolbox']
    use_gpu_encoder = encoder in gpu_encoders
    encoder_info = f"GPU ({encoder})" if use_gpu_encoder else f"CPU ({encoder})"
    print(f"\n--- PHASE 3: EXTRACTING, ADDING TRANSITIONS, & COMBINING (Re-encoding)---")
    print(f"Applying transitions using the {encoder_info} encoder. This process may take some time.")
    with tempfile.TemporaryDirectory() as tempdir:
        temp_files_for_concat = []
        for i, start_time in enumerate(start_times):
            temp_filename = os.path.join(tempdir, f"temp_clip_{i+1}.mp4")
            print(f"\n[INFO] Extracting clip {i+1} of {len(start_times)} (starts at {start_time:.2f}s)...")
            command_extract = ["ffmpeg", "-y", "-ss", str(start_time), "-i", input_file, "-t", str(clip_duration), "-an", temp_filename]
            try:
                subprocess.run(command_extract, check=True, capture_output=True)
                print(f"[SUCCESS] Clip {i+1} extracted.")
                temp_files_for_concat.append(temp_filename)
            except subprocess.CalledProcessError as e:
                error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg error."
                print(f"\n[ERROR] Failed to extract clip at {start_time:.2f}s:\n{error_message}")

        if not temp_files_for_concat:
            print("[ERROR] No clips were successfully extracted. Final video cannot be created.")
            return False
        print("\n[INFO] Building filtergraph for transitions and stitching final video...")
        command_concat = ["ffmpeg", "-y"]
        if 'nvenc' in encoder:
            command_concat.extend(['-init_hw_device', f'cuda=cuda:{cuda_device}'])
            command_concat.extend(['-filter_hw_device', 'cuda'])
        for f in temp_files_for_concat: command_concat.extend(["-i", f])
        filter_complex = ""
        fade_end_point = clip_duration - fade_duration
        for i in range(len(temp_files_for_concat)):
            filter_complex += f"[{i}:v]fade=type=out:start_time={fade_end_point}:duration={fade_duration}:color=white[v{i}_fadeout];"
            if i > 0: filter_complex += f"[v{i}_fadeout]fade=type=in:start_time=0:duration={fade_duration}:color=white[v{i}_final];"
            else: filter_complex += f"[v{i}_fadeout]null[v{i}_final];"
        concat_inputs = "".join([f"[v{i}_final]" for i in range(len(temp_files_for_concat))])
        if use_gpu_encoder:
            filter_complex += f"{concat_inputs}concat=n={len(temp_files_for_concat)}:v=1:a=0[v_cpu]; [v_cpu]format=yuv420p,hwupload[v]"
            command_concat.extend(["-c:v", encoder])
            if 'nvenc' in encoder: command_concat.extend(['-preset', 'fast'])
        else:
            filter_complex += f"{concat_inputs}concat=n={len(temp_files_for_concat)}:v=1:a=0[v]"
            command_concat.extend(["-c:v", encoder, "-preset", "veryfast", "-crf", "23"])
        command_concat.extend(["-filter_complex", filter_complex, "-map", "[v]", output_file])
        try:
            subprocess.run(command_concat, check=True, capture_output=True)
            print("[SUCCESS] Final video with transitions stitched.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg concat error."
            print(f"[ERROR] Failed to combine clips with transitions.\nFull Command: {' '.join(shlex.quote(c) for c in command_concat)}\nError:\n{error_message}")
            return False
    print(f"\n-------------------------------------------------\n         PROCESS COMPLETE\nYour hook video has been saved as: {output_file}\n-------------------------------------------------")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Creates a hook video using FFmpeg. Analysis can be GPU accelerated (OpenCL), and transition encoding can be GPU accelerated (NVENC, AMF, VideoToolbox).",
        epilog=("Example (fast, no transitions): python create_hook.py \"my_video.mp4\" 5 1 --gpu\n"
                "Example (CPU transitions): python create_hook.py \"my_video.mp4\" 5 1 --transition white\n"
                "Example (GPU transitions with NVIDIA): python create_hook.py \"my_video.mp4\" 5 1 --transition white --encoder hevc_nvenc\n"
                "Example (Peak action scoring): python create_hook.py \"my_video.mp4\" 5 1 --scoring peak\n"
                "Example (Focused analysis): python create_hook.py \"my_video.mp4\" 5 1 --center_focus 0.5")
    )
    parser.add_argument("input", help="Path to the input video file.")
    parser.add_argument("num_clips", type=int, help="The number of clips to find.")
    parser.add_argument("clip_duration", type=float, help="The duration of each clip.")
    parser.add_argument("-o", "--output", default="output.mp4", help="Name of the output file. (default: output.mp4)")
    parser.add_argument("-t", "--threshold", type=float, default=0.005, help="Motion detection sensitivity for analysis phase. (default: 0.005)")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    parser.add_argument("--end", type=float, help="End time in source video (seconds).")
    parser.add_argument("--gpu", default=True, help="Use GPU (OpenCL) for the analysis phase. Does not affect encoding.")
    parser.add_argument("--cl_device", type=str, default="0.0", help="The OpenCL device to use for analysis. (default: 0.0)")
    parser.add_argument('--transition', default='white', choices=['white'], help="Adds a 'dip to white' transition. This requires re-encoding the video.")
    parser.add_argument('--encoder', type=str, default='hevc_nvenc', help="Video encoder to use when transitions are enabled. (default: 'libx264'). Hardware options: 'h264_nvenc', 'hevc_nvenc' (NVIDIA), 'h264_videotoolbox' (macOS), 'h264_amf' (AMD).")
    parser.add_argument('--scoring', choices=['sum', 'peak'], default='sum', help="Scoring method. 'sum': finds windows with highest total motion (good for sustained action). 'peak': finds windows with the highest single motion spike (good for jumps, impacts). Default: sum.")
    parser.add_argument('--center_focus', type=float, default=0.4, help="Focus analysis on the center of the video. Value from 0.1 to 1.0 (e.g., 0.5 for the center 50%%). Analysis only.")
    parser.add_argument('--cuda_device', type=str, default='0', help="CUDA device index for NVENC encoding (default: '0').")

    args = parser.parse_args()
    if not os.path.exists(args.input): sys.exit(f"Error: Input file not found at '{args.input}'")
    if not check_ffmpeg(): sys.exit(1)
    log_file_path = "scene_scores_temp.log"
    video_created_successfully = False
    if os.path.exists(log_file_path):
        print(f"\n[INFO] Found existing '{log_file_path}'. Skipping analysis phase.")
        analysis_completed = True
    else:
        analysis_completed = analyze_video(args.input, args.threshold, args.gpu, args.cl_device, start_time=args.start, end_time=args.end, center_focus=args.center_focus)

    if analysis_completed:
        start_times = find_most_active_clips(log_file_path, args.clip_duration, args.num_clips, scoring_method=args.scoring)
        if start_times:
            if args.transition == 'white':
                video_created_successfully = extract_and_fade_combine(args.input, start_times, args.clip_duration, args.output, encoder=args.encoder, cuda_device=args.cuda_device)
            else:
                video_created_successfully = extract_and_combine(args.input, start_times, args.clip_duration, args.output)

    if video_created_successfully:
        print(f"\n[INFO] Successfully created video. Removing '{log_file_path}'.")
        try:
            if os.path.exists(log_file_path):
                os.remove(log_file_path)
        except OSError as e:
            print(f"[WARNING] Could not remove log file: {e}")
    else:
        print(f"\n[INFO] Process did not complete successfully. '{log_file_path}' has been kept for debugging.")

if __name__ == "__main__":
    main()