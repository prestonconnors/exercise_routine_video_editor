# run_workflow.py (Improved with --start and real-time output fix)

import argparse
import os
import subprocess
import sys
import yaml

# --- Configuration ---
BGM_OUTPUT_FILENAME = "background_music.m4a"
FINAL_VIDEO_FILENAME_SUFFIX = "_final.mp4"
# --- End Configuration ---

def run_command(command):
    """Executes a command and prints its output in real-time."""
    print(f"\n🚀 EXECUTE: {' '.join(command)}")
    try:
        # --- FIX for real-time output ---
        # By setting PYTHONUNBUFFERED, we tell the child Python process
        # not to buffer its output, so we receive it line-by-line.
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace', # Prevents errors on unusual characters
            env=env # Pass the modified environment to the child process
        )
        # Read and print output line by line
        for line in iter(process.stdout.readline, ''):
            sys.stdout.write(line)
        
        process.stdout.close()
        return_code = process.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, command)
            
    except FileNotFoundError:
        print(f"❌ ERROR: Command '{command[0]}' not found.")
        print("Please ensure Python, FFmpeg, and FFprobe are installed and in your system's PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Command failed with exit code {e.returncode}.")
        sys.exit(1)

def main(routine_path, source_video_path, start_offset): # <-- Added start_offset argument
    # This will be the full path to your venv's python.exe
    python_executable = sys.executable 
    
    # 1. Validate input files
    if not os.path.exists(routine_path):
        print(f"❌ ERROR: Routine file not found at '{routine_path}'")
        sys.exit(1)
    if not os.path.exists(source_video_path):
        print(f"❌ ERROR: Source video not found at '{source_video_path}'")
        sys.exit(1)

    # === WORKFLOW STEP 5: GENERATE TIMER ASSETS ===
    # (This section is unchanged)
    print("▶️ STEP 5: Generating Timer Assets")
    try:
        with open(routine_path, 'r', encoding='utf-8') as f:
            routine_data = yaml.safe_load(f)
            if not isinstance(routine_data, list):
                print(f"❌ ERROR: Invalid routine file format in '{routine_path}'. It should be a list.")
                sys.exit(1)
            unique_lengths = set()
            for item in routine_data:
                if 'length' in item and isinstance(item['length'], (int, float)):
                    unique_lengths.add(int(item['length']))
    except yaml.YAMLError as e:
        print(f"❌ ERROR: Could not parse YAML file '{routine_path}'. Reason: {e}")
        sys.exit(1)

    if not unique_lengths:
        print("⚠️ WARNING: No segment lengths found. Skipping timer generation.")
    else:
        print(f"✅ Found {len(unique_lengths)} unique timer duration(s): {sorted(list(unique_lengths))}")
        for length in sorted(list(unique_lengths)):
            run_command([python_executable, "create_progress_ring.py", str(length)])

    # === WORKFLOW STEP 6: GENERATE THE BACKGROUND MUSIC TRACK ===
    print("\n▶️ STEP 6: Generating Background Music Track")
    run_command([python_executable, "create_background_music.py", routine_path, BGM_OUTPUT_FILENAME])

    # === WORKFLOW STEP 7: ASSEMBLE THE FINAL VIDEO ===
    print("\n▶️ STEP 7: Assembling Final Video")
    output_video_name = os.path.splitext(os.path.basename(routine_path))[0] + FINAL_VIDEO_FILENAME_SUFFIX
    print(f"✅ Final video will be saved as: {output_video_name}")
    
    assembly_command = [
        python_executable,
        "assemble_video.py",
        routine_path,
        source_video_path,
        output_video_name,
        "--bgm",
        BGM_OUTPUT_FILENAME
    ]
    
    # --- ADDED --start argument passing ---
    if start_offset > 0.0:
        assembly_command.extend(["--start", str(start_offset)])

    run_command(assembly_command)

    print(f"\n🎉 Workflow complete! Your video is ready at: {output_video_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automated workflow for generating exercise videos.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("routine_file", help="Path to the exercise routine YAML file.")
    parser.add_argument("source_video", help="Path to the source video file.")
    # --- ADDED --start argument definition ---
    parser.add_argument("--start", type=float, default=0.0, help="Start time in the source video (seconds) to begin the routine from.")

    args = parser.parse_args()
    main(args.routine_file, args.source_video, args.start) # <-- Pass the new argument