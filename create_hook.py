import subprocess
import os
import argparse
import sys
import operator
import tempfile
import shlex
import json

try:
    import yaml
except ImportError:
    print("[ERROR] The 'PyYAML' library is required for the new routine-based analysis.")
    print("Please install it by running: pip install PyYAML")
    sys.exit(1)

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
    (Legacy Method) Parses a log file to find the start times of the most active clips across the whole video.
    """
    print("\n--- PHASE 2: PARSING RESULTS (Standard Method)---")
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

def find_active_clips_by_routine(log_file, routine_path, num_clips, clip_duration):
    """
    Finds the most active clips, prioritizing unique exercises from the routine.yaml file.
    If not enough unique exercises are found, it fills the remaining slots with the next most-active clips.
    """
    print("\n--- PHASE 2: PARSING RESULTS (Routine-Based Method) ---")
    
    # 1. Parse the FFmpeg log file to get all motion scores
    all_scores = []
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
                        all_scores.append({'ts': timestamp, 'score': score})
                    except (ValueError, IndexError): pass
                i += 2 # Process in pairs of lines
    except FileNotFoundError:
        print(f"[ERROR] Log file '{log_file}' not found. Analysis likely failed.")
        return []

    if not all_scores:
        print("[WARNING] No motion frames were detected. Consider lowering the --threshold.")
        return []
    
    # 2. Parse the YAML routine file and define segment boundaries
    print(f"[INFO] Parsing routine from '{routine_path}'...")
    with open(routine_path, 'r') as f:
        routine_data = yaml.safe_load(f)

    segments = []
    current_time = 0.0
    ignore_keywords = ['intro', 'warmup', 'rest', 'cool down', 'outro']
    for item in routine_data:
        length = float(item.get('length', 0))
        name = item.get('name', 'Unknown')
        is_action_segment = not any(keyword in name.lower() for keyword in ignore_keywords)
        
        segments.append({
            'name': name,
            'start': current_time,
            'end': current_time + length,
            'is_action': is_action_segment,
            'total_score': 0.0,
            'scores': []
        })
        current_time += length
    
    action_segments = [s for s in segments if s['is_action']]
    print(f"[INFO] Identified {len(action_segments)} action segments to analyze.")
    
    # 3. Assign each score from the log to its corresponding segment
    for score_event in all_scores:
        for segment in action_segments:
            if segment['start'] <= score_event['ts'] < segment['end']:
                segment['scores'].append(score_event)
                segment['total_score'] += score_event['score']
                break 
    
    # 4. Select top segments with a preference for unique exercise names
    print("[INFO] Selecting segments with a preference for unique exercises...")
    all_sorted_segments = sorted([s for s in action_segments if s['total_score'] > 0], key=lambda s: s['total_score'], reverse=True)
    
    top_segments = []
    seen_names = set()

    # First pass: Get the best instance of each unique exercise
    for segment in all_sorted_segments:
        if len(top_segments) >= num_clips:
            break
        if segment['name'] not in seen_names:
            top_segments.append(segment)
            seen_names.add(segment['name'])

    # Second pass: If we still need more clips, fill with the best remaining ones
    if len(top_segments) < num_clips:
        print(f"[INFO] Not enough unique exercises with detected motion. Adding duplicates from the most active remaining segments.")
        existing_starts = {s['start'] for s in top_segments}
        for segment in all_sorted_segments:
            if len(top_segments) >= num_clips:
                break
            if segment['start'] not in existing_starts:
                 top_segments.append(segment)
                 existing_starts.add(segment['start'])

    if not top_segments:
        print("[WARNING] Could not find any action segments with motion scores.")
        return []

    top_segments.sort(key=lambda s: s['total_score'], reverse=True)
        
    print(f"\n[INFO] Top {len(top_segments)} most active exercise segments selected:")
    for i, seg in enumerate(top_segments):
        print(f"  {i+1}. {seg['name']} (Score: {seg['total_score']:.2f})")

    # 5. For each top segment, find the highest-scoring clip within it
    final_start_times = []
    for segment in top_segments:
        if not segment['scores']:
            continue
        
        window_scores = {}
        for score_event in segment['scores']:
            offset_in_segment = score_event['ts'] - segment['start']
            if offset_in_segment > (segment['end'] - segment['start'] - clip_duration):
                continue
            
            window_start_time = segment['start'] + (int(offset_in_segment / clip_duration) * clip_duration)
            
            current_score = window_scores.get(window_start_time, 0)
            window_scores[window_start_time] = current_score + score_event['score']

        if window_scores:
            best_clip_start_time = max(window_scores, key=window_scores.get)
            final_start_times.append(best_clip_start_time)
            print(f"  -> Found best clip in '{segment['name']}' starting at {best_clip_start_time:.2f}s")
            
    if not final_start_times:
        print("[WARNING] Could not find any high-motion clips within the top segments.")
        return []

    print(f"\n[SUCCESS] Selected {len(final_start_times)} clip start times for the final video.")
    return sorted(final_start_times)

def extract_and_combine(input_file, start_times, clip_duration, output_file, encoder, speed_factor=1.0):
    print("\n--- PHASE 3: EXTRACTING & COMBINING CLIPS ---")
    if speed_factor > 1.0:
        print(f"Applying {speed_factor:.2f}x speed up. Re-encoding is required.")
    else:
        print("Using stream copy for fast video extraction (no re-encoding).")

    with tempfile.TemporaryDirectory() as tempdir:
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
                print(f"\n[ERROR] Failed to extract clip at {start_time:.2f}s:\n{e.stderr.decode()}")
                continue

        if not temp_files_for_concat:
            print("[ERROR] No clips were successfully extracted. Final video cannot be created.")
            return False

        print("\n[INFO] Stitching final video...")
        
        if speed_factor > 1.0:
            concat_cmd = ["ffmpeg", "-y"]
            for f in temp_files_for_concat: concat_cmd.extend(["-i", f])
            concat_inputs = "".join([f"[{i}:v]" for i in range(len(temp_files_for_concat))])
            filter_complex = f"{concat_inputs}concat=n={len(temp_files_for_concat)}:v=1:a=0[cat];[cat]setpts=PTS/{speed_factor:.4f}[v]"
            concat_cmd.extend(["-filter_complex", filter_complex, "-map", "[v]"])
            concat_cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
            concat_cmd.append(output_file)
        else:
            file_list_path = os.path.join(tempdir, "files.txt")
            with open(file_list_path, "w") as f:
                for temp_file in temp_files_for_concat:
                    f.write(f"file '{temp_file.replace(os.sep, '/')}'\n")
            concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_path, "-c", "copy", output_file]

        try:
            subprocess.run(concat_cmd, check=True, capture_output=True)
            print("[SUCCESS] Final video stitched.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg concat error."
            full_command_str = ' '.join(shlex.quote(c) for c in concat_cmd)
            print(f"[ERROR] Failed to combine clips.\nFull Command: {full_command_str}\nError: {error_message}")
            return False
            
    print(f"\n-------------------------------------------------\n         PROCESS COMPLETE\nYour hook video has been saved as: {output_file}\n-------------------------------------------------")
    return True

def extract_and_fade_combine(input_file, start_times, clip_duration, output_file, fade_duration=0.25, encoder="libx264", cuda_device="0", speed_factor=1.0):
    gpu_encoders = ['h264_nvenc', 'hevc_nvenc', 'h264_amf', 'hevc_amf', 'h264_videotoolbox']
    use_gpu_encoder = encoder in gpu_encoders
    encoder_info = f"GPU ({encoder})" if use_gpu_encoder else f"CPU ({encoder})"
    print(f"\n--- PHASE 3: EXTRACTING, ADDING TRANSITIONS, & COMBINING (Re-encoding)---")
    print(f"Applying transitions using the {encoder_info} encoder. This process may take some time.")
    if speed_factor > 1.0:
        print(f"Applying {speed_factor:.2f}x speed up to the final video.")

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
                print(f"\n[ERROR] Failed to extract clip at {start_time:.2f}s:\n{e.stderr.decode()}")
                continue

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
        
        speed_filter = f"setpts=PTS/{speed_factor:.4f}" if speed_factor > 1.0 else "null"
        
        if use_gpu_encoder:
            filter_complex += f"{concat_inputs}concat=n={len(temp_files_for_concat)}:v=1:a=0[v_cat]; [v_cat]{speed_filter},format=yuv420p,hwupload[v]"
            command_concat.extend(["-c:v", encoder])
            if 'nvenc' in encoder: command_concat.extend(['-preset', 'fast'])
        else:
            filter_complex += f"{concat_inputs}concat=n={len(temp_files_for_concat)}:v=1:a=0[v_cat]; [v_cat]{speed_filter}[v]"
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
        description="Creates a hook video using FFmpeg by finding the most active clips.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "--- EXAMPLES ---\n\n"
            "# Create a 5-second hook from 4x 2-second clips (total 8s), sped up to fit\n"
            "python create_hook.py \"my_video.mp4\" 4 2.0 --max_duration 5.0 --routine \"routine.yaml\"\n\n"
            "# Find the 5 best 1-second clips, prioritizing unique exercises\n"
            "python create_hook.py \"my_video.mp4\" 5 1 --routine \"path/to/routine.yaml\"\n\n"
            "# Old method without a routine file\n"
            "python create_hook.py \"my_video.mp4\" 5 1 --gpu"
        )
    )
    routine_group = parser.add_argument_group('Routine-Based Analysis (New Method)')
    routine_group.add_argument("--routine", help="Path to the routine.yaml file. This enables the new analysis method.")
    
    standard_group = parser.add_argument_group('Standard Arguments')
    standard_group.add_argument("input", help="Path to the input video file.")
    standard_group.add_argument("num_clips", type=int, help="The number of clips to find.")
    standard_group.add_argument("clip_duration", type=float, help="The duration of each individual clip.")
    standard_group.add_argument("-o", "--output", default="output.mp4", help="Name of the output file. (default: output.mp4)")
    standard_group.add_argument("-t", "--threshold", type=float, default=0.005, help="Motion detection sensitivity. Lower is more sensitive. (default: 0.005)")
    standard_group.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    standard_group.add_argument("--end", type=float, help="End time in source video (seconds).")

    adv_group = parser.add_argument_group('Performance and Advanced Options')
    adv_group.add_argument('--max_duration', type=float, help="Maximum final video duration. Speeds up the video to fit if needed.")
    adv_group.add_argument("--gpu", action=argparse.BooleanOptionalAction, default=True, help="Use GPU (OpenCL) for the analysis phase. Does not affect encoding. Default is on.")
    adv_group.add_argument("--cl_device", type=str, default="0.0", help="The OpenCL device to use for analysis. (default: 0.0)")
    adv_group.add_argument('--transition', choices=[None, 'white'], default=None, help="Adds a 'dip to white' transition. This requires re-encoding.")
    adv_group.add_argument('--encoder', type=str, default='hevc_nvenc', help="Video encoder for transitions. HW options: h264_nvenc, hevc_nvenc (NVIDIA), h264_videotoolbox (macOS), h264_amf (AMD). (default: hevc_nvenc)")
    adv_group.add_argument('--scoring', choices=['sum', 'peak'], default='sum', help="[Legacy] Scoring method for non-routine analysis. 'sum' for sustained action, 'peak' for spikes. Default: sum.")
    adv_group.add_argument('--center_focus', type=float, help="Focus analysis on the center X%% of the video (value from 0.1 to 1.0).")
    adv_group.add_argument('--cuda_device', type=str, default='0', help="CUDA device index for NVENC encoding (default: '0').")

    args = parser.parse_args()

    if not os.path.exists(args.input): sys.exit(f"Error: Input file not found at '{args.input}'")
    if args.routine and not os.path.exists(args.routine): sys.exit(f"Error: Routine file not found at '{args.routine}'")
    if not check_ffmpeg(): sys.exit(1)
    
    log_file_path = "scene_scores_temp.log"
    video_created_successfully = False
    
    if os.path.exists(log_file_path):
        print(f"\n[INFO] Found existing '{log_file_path}'. Skipping analysis phase.")
        analysis_completed = True
    else:
        analysis_completed = analyze_video(
            args.input, args.threshold, args.gpu, args.cl_device, 
            start_time=args.start, end_time=args.end, center_focus=args.center_focus
        )

    if analysis_completed:
        start_times = []
        if args.routine:
            start_times = find_active_clips_by_routine(
                log_file_path, args.routine, args.num_clips, args.clip_duration
            )
        else:
            start_times = find_most_active_clips(
                log_file_path, args.clip_duration, args.num_clips, scoring_method=args.scoring
            )
        
        if start_times:
            speed_factor = 1.0
            if args.max_duration and args.max_duration > 0:
                total_clip_time = len(start_times) * args.clip_duration
                if total_clip_time > args.max_duration:
                    speed_factor = total_clip_time / args.max_duration
            
            if args.transition == 'white':
                video_created_successfully = extract_and_fade_combine(
                    args.input, start_times, args.clip_duration, args.output, 
                    encoder=args.encoder, cuda_device=args.cuda_device, speed_factor=speed_factor
                )
            else:
                video_created_successfully = extract_and_combine(
                    args.input, start_times, args.clip_duration, args.output,
                    encoder=args.encoder, speed_factor=speed_factor
                )

    if video_created_successfully:
        print(f"\n[SUCCESS] Video creation complete. Removing temporary log file.")
        '''if os.path.exists(log_file_path):
            try:
                os.remove(log_file_path)
            except OSError as e:
                print(f"[WARNING] Could not remove log file '{log_file_path}': {e}")'''
    else:
        print(f"\n[FAILURE] Process did not complete successfully. The log file '{log_file_path}' has been kept for debugging.")

if __name__ == "__main__":
    main()