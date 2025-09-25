import subprocess
import os
import argparse
import sys
import operator
import tempfile
import shlex

def check_ffmpeg():
    """Checks if FFmpeg is installed and in the system's PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("FFmpeg found.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: FFmpeg is not installed or not in your system's PATH.")
        return False

def analyze_video(input_file, threshold, use_gpu=False, cl_device="0.0"):
    """
    Analyzes the video file using the correctly quoted filterchain.
    """
    print(f"\n--- PHASE 1: ANALYZING VIDEO FOR MOTION ---")
    if use_gpu:
        print(f"Using GPU acceleration (OpenCL Method on device {cl_device})")
    else:
        print(f"Using CPU for analysis")
    
    log_filename = "scene_scores_temp.log"

    command = ["ffmpeg", "-y"]

    if use_gpu:
        command.extend(["-init_hw_device", f"opencl=ocl:{cl_device}"])

    command.extend(["-i", input_file])

    if use_gpu:
        filter_chain = f"hwupload,hwdownload,format=p010le,select='gt(scene,{threshold})',metadata=print:file={log_filename}"
        command.extend(["-filter_hw_device", "ocl", "-vf", filter_chain])
    else:
        filter_chain = f"select='gt(scene,{threshold})',metadata=print:file={log_filename}"
        command.extend(["-vf", filter_chain])

    command.extend(["-f", "null", "-"])
    
    try:
        print("\n[INFO] Starting FFmpeg scene analysis. See live progress below:")
        print("----------------------------------------------------------------------")
        subprocess.run(["ffmpeg", "-y"] + command[2:], check=True, stdout=subprocess.DEVNULL)
        print("\n----------------------------------------------------------------------")
        print("[SUCCESS] FFmpeg analysis complete.")
        return True
    except subprocess.CalledProcessError as e:
        error_message = e.stderr if hasattr(e, 'stderr') and e.stderr else "Unknown FFmpeg error."
        print(f"\n[ERROR] FFmpeg analysis failed:\n{error_message}")
        return False
    except KeyboardInterrupt:
        print("\n\n[INFO] Process cancelled by user.")
        return False

def find_most_active_clips(log_file, clip_duration_sec, num_clips):
    """
    Parses a two-line log format to find the start times of the most active clips.
    """
    print("\n--- PHASE 2: PARSING RESULTS ---")
    print("Finding the most active scenes from the analysis log...")
    scene_scores = {}
    
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            i = 0
            while i < len(lines) - 1:
                current_line = lines[i]
                next_line = lines[i+1]
                
                if "pts_time:" in current_line and "lavfi.scene_score=" in next_line:
                    try:
                        time_parts = current_line.strip().split()
                        time_str = [p for p in time_parts if p.startswith("pts_time:")][0]
                        timestamp = float(time_str.split(':')[1])

                        score_str = next_line.strip()
                        score = float(score_str.split('=')[1])
                        
                        interval_start = int(timestamp / clip_duration_sec) * clip_duration_sec
                        scene_scores.setdefault(interval_start, 0)
                        scene_scores[interval_start] += score
                        i += 2
                    except (ValueError, IndexError):
                        i += 1
                else:
                    i += 1

    except FileNotFoundError:
        print(f"Error: Log file '{log_file}' not found. Analysis likely failed.")
        return []

    if not scene_scores:
        print("[WARNING] Could not detect any motion with the current threshold.")
        print("          Try running again with a more sensitive (lower) --threshold value.")
        return []
    
    sorted_clips = sorted(scene_scores.items(), key=operator.itemgetter(1), reverse=True)
    print(f"[SUCCESS] Found {len(sorted_clips)} potential time windows. Selecting the top {num_clips}.")
    top_start_times = sorted([clip[0] for clip in sorted_clips[:num_clips]])
    return top_start_times

def extract_and_combine(input_file, start_times, clip_duration, output_file):
    """
    Extracts clips using stream copy for maximum speed without re-encoding.
    """
    print("\n--- PHASE 3: EXTRACTING & COMBINING CLIPS (No Re-encoding)---")
    print("Using stream copy for fast video extraction. This process is very fast and does not use the GPU for encoding.")

    with tempfile.TemporaryDirectory() as tempdir:
        file_list_path = os.path.join(tempdir, "files.txt")
        temp_files_for_concat = []

        for i, start_time in enumerate(start_times):
            temp_filename = os.path.join(tempdir, f"temp_clip_{i+1}.mp4")
            
            print(f"\n[INFO] Extracting clip {i+1} of {len(start_times)} (starts at {start_time:.2f}s)...")
            
            # Use input seeking (-ss before -i) for speed.
            # Use -c copy to avoid re-encoding.
            command_extract = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-i", input_file,
                "-t", str(clip_duration),
                "-c", "copy",
                "-an",  # No audio
                temp_filename
            ]

            try:
                # Use capture_output to hide ffmpeg's verbose output for successful runs
                subprocess.run(command_extract, check=True, capture_output=True)
                print(f"[SUCCESS] Clip {i+1} extracted.")
                temp_files_for_concat.append(temp_filename)
            except subprocess.CalledProcessError as e:
                # Provide more detailed error info if a clip fails
                error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg error."
                print(f"\n[ERROR] Failed to extract clip at {start_time:.2f}s:\n{error_message}")
                print("\n[HINT] This can sometimes happen if cutting at this exact timestamp isn't possible with stream copy. The process will continue with the successfully extracted clips.")


        with open(file_list_path, "w") as f:
            for temp_file in temp_files_for_concat:
                f.write(f"file '{temp_file.replace(os.sep, '/')}'\n")
        
        if not temp_files_for_concat:
             print("[ERROR] No clips were successfully extracted. Final video cannot be created.")
             return False

        print("\n[INFO] Stitching final video...")
        concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_path, "-c", "copy", output_file]
        
        try:
            subprocess.run(concat_cmd, check=True, capture_output=True)
            print("[SUCCESS] Final video stitched.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else "Unknown FFmpeg concat error."
            print(f"[ERROR] Failed to combine clips.\n{error_message}")
            return False
    
    print("\n-------------------------------------------------")
    print("         PROCESS COMPLETE")
    print(f"Your hook video has been saved as: {output_file}")
    print("-------------------------------------------------")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Creates a hook video using OpenCL for analysis and fast, direct stream copying for extraction.",
        epilog=("Example: python create_hook.py \"my_video.mp4\" 5 1 --gpu --threshold 0.01")
    )
    parser.add_argument("input", help="Path to the input video file.")
    parser.add_argument("num_clips", type=int, help="The number of clips to find.")
    parser.add_argument("clip_duration", type=float, help="The duration of each clip.")
    parser.add_argument("-o", "--output", default="output.mp4", help="Name of the output file.")
    parser.add_argument("-t", "--threshold", type=float, default=0.04, help="Motion detection sensitivity.")
    parser.add_argument("--gpu", action="store_true", help="Use GPU acceleration for the analysis phase.")
    parser.add_argument("--cl_device", type=str, default="0.0", help="The OpenCL device to use for analysis.")
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        sys.exit(f"Error: Input file not found at '{args.input}'")
    if not check_ffmpeg():
        sys.exit(1)
    
    log_file_path = "scene_scores_temp.log"
    video_created_successfully = False

    analysis_needed = not os.path.exists(log_file_path)
    analysis_completed = False

    if analysis_needed:
        if analyze_video(args.input, args.threshold, args.gpu, args.cl_device):
            analysis_completed = True
    else:
        print(f"\n[INFO] Found existing '{log_file_path}'. Skipping analysis phase.")
        analysis_completed = True

    if analysis_completed:
        start_times = find_most_active_clips(log_file_path, args.clip_duration, args.num_clips)
        if start_times:
            if extract_and_combine(args.input, start_times, args.clip_duration, args.output):
                video_created_successfully = True

    if video_created_successfully:
        print(f"\n[INFO] Successfully created video. Removing '{log_file_path}'.")
        os.remove(log_file_path)
    else:
        print(f"\n[INFO] Process did not complete successfully. '{log_file_path}' has been kept for debugging.")


if __name__ == "__main__":
    main()