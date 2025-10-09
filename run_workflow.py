# run_workflow.py (Generates hook video as the intro if specified in YAML)

import argparse
import os
import subprocess
import sys
import yaml

# --- Configuration & Defaults ---
BGM_OUTPUT_FILENAME = "background_music.m4a"
FINAL_VIDEO_FILENAME_SUFFIX = "_final.mp4"
HOOK_VIDEO_FILENAME_SUFFIX = "_hook.mp4"

# Defaults for the hook video creation step
HOOK_CLIPS = 5
HOOK_DURATION_SEC = 1.0
HOOK_CENTER_FOCUS = 0.4
# --- End Configuration ---

def run_command(command):
    """Executes a command and prints its output in real-time."""
    print(f"\n🚀 EXECUTE: {' '.join(command)}")
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
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

def main(args):
    """Main workflow function."""
    python_executable = sys.executable 
    
    # 1. Validate input files
    if not os.path.exists(args.routine_file):
        print(f"❌ ERROR: Routine file not found at '{args.routine_file}'")
        sys.exit(1)
    if not os.path.exists(args.source_video):
        print(f"❌ ERROR: Source video not found at '{args.source_video}'")
        sys.exit(1)

    # === Pre-load routine data to be used in multiple steps ===
    try:
        with open(args.routine_file, 'r', encoding='utf-8') as f:
            routine_data = yaml.safe_load(f)
            if not isinstance(routine_data, list):
                print(f"❌ ERROR: Invalid routine file format in '{args.routine_file}'. It should be a list of segments.")
                sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ ERROR: Could not parse YAML file '{args.routine_file}'. Reason: {e}")
        sys.exit(1)

    '''# === WORKFLOW STEP 5: GENERATE TIMER ASSETS ===
    print("▶️ STEP 5: Generating Timer Assets")
    unique_lengths = set(int(item['length']) for item in routine_data if 'length' in item and isinstance(item['length'], (int, float)))

    if not unique_lengths:
        print("⚠️ WARNING: No segment lengths found. Skipping timer generation.")
    else:
        print(f"✅ Found {len(unique_lengths)} unique timer duration(s): {sorted(list(unique_lengths))}")
        for length in sorted(list(unique_lengths)):
            run_command([python_executable, "create_progress_ring.py", str(length)])'''

    # === WORKFLOW STEP 6: GENERATE THE BACKGROUND MUSIC TRACK ===
    print("\n▶️ STEP 6: Generating Background Music Track")
    run_command([python_executable, "create_background_music.py", args.routine_file, BGM_OUTPUT_FILENAME])

    # === WORKFLOW STEP 7: CREATE HOOK VIDEO ===
    print("\n▶️ STEP 7: Creating Action Hook Video")
    
    # --- New logic to find the intro video path ---
    hook_output_path = None
    for segment in routine_data:
        # Check for name being 'intro' (case-insensitive) and existence of replace_video key
        if segment.get('name', '').lower() == 'intro' and 'replace_video' in segment:
            hook_output_path = segment['replace_video']
            print(f"✅ Found 'intro' segment with 'replace_video'. Setting hook output to overwrite: {hook_output_path}")
            break # Found it, no need to keep searching

    # Fallback if no intro with a 'replace_video' path was found
    if not hook_output_path:
        hook_output_path = os.path.splitext(os.path.basename(args.routine_file))[0] + HOOK_VIDEO_FILENAME_SUFFIX
        print(f"✅ No 'intro' segment found for replacement. Saving hook video to default path: {hook_output_path}")

    hook_command = [
        python_executable, "create_hook.py",
        args.source_video,
        str(HOOK_CLIPS),
        str(HOOK_DURATION_SEC),
        "--output", hook_output_path,
        "--center_focus", str(HOOK_CENTER_FOCUS),
        #"--gpu" # Keep GPU analysis enabled by default for speed
    ]
    
    if args.start > 0.0:
        hook_command.extend(["--start", str(args.start)])

    run_command(hook_command)

    # === WORKFLOW STEP 8: ASSEMBLE THE FINAL VIDEO ===
    print("\n▶️ STEP 8: Assembling Final Video")
    output_video_name = os.path.splitext(os.path.basename(args.routine_file))[0] + FINAL_VIDEO_FILENAME_SUFFIX
    print(f"✅ Final video will be saved as: {output_video_name}")
    
    assembly_command = [
        python_executable, "assemble_video.py",
        args.routine_file,
        args.source_video,
        output_video_name,
        "--bgm", BGM_OUTPUT_FILENAME
    ]
    
    if args.start > 0.0:
        assembly_command.extend(["--start", str(args.start)])

    run_command(assembly_command)

    print(f"\n🎉 Workflow complete!")
    print(f"   Final video saved to: {output_video_name}")
    print(f"   Hook video saved to: {hook_output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automated workflow for generating exercise and hook videos.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # Core arguments
    parser.add_argument("routine_file", help="Path to the exercise routine YAML file.")
    parser.add_argument("source_video", help="Path to the source video file.")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in the source video (seconds) to begin the routine and hook analysis from.")

    args = parser.parse_args()
    main(args)