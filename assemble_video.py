import os
import sys
import yaml
import textwrap
import subprocess
import argparse
import time
from pathlib import Path
import shutil

# --- Helper Functions ---
def sanitize_text_for_ffmpeg(text: str) -> str:
    """Escapes characters that are special to FFmpeg's drawtext filter."""
    text = text.replace('\\', '\\\\')
    text = text.replace("'", "'\\\\\\''")
    text = text.replace('"', '\\"')
    text = text.replace('%', '\\%')
    text = text.replace(':', '\\:')
    return text

def prepare_text_for_ffmpeg(text: str, line_width: int = 25) -> str:
    """Wraps text and sanitizes it for the drawtext filter."""
    wrapped_lines = textwrap.wrap(text, width=line_width, break_long_words=True, replace_whitespace=True)
    wrapped_text = "\n".join(wrapped_lines)
    return sanitize_text_for_ffmpeg(wrapped_text)

# --- Main Logic ---
def assemble_video(
    config_path: str, 
    routine_path: str, 
    source_video_path: str, 
    output_path: str, 
    segments_to_process: list[int] | None = None,
    source_start_offset: float = 0.0,
    source_end_limit: float | None = None,
    test_mode: bool = False,
    verbose_mode: bool = False
):
    total_start_time = time.monotonic()
    
    try:
        with open(config_path, 'r') as f: cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FATAL: Config file not found at '{config_path}'"); sys.exit(1)
    try:
        with open(routine_path, 'r') as f: routine = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FATAL: Routine file not found at '{routine_path}'"); sys.exit(1)
    if not os.path.exists(source_video_path):
        print(f"FATAL: Source video not found at '{source_video_path}'"); sys.exit(1)

    paths_cfg, video_cfg, title_cfg, ring_cfg, source_cfg, finish_cfg = (
        cfg['paths'], cfg['video_output'].copy(), cfg['text_overlays']['exercise_name'], 
        cfg['progress_ring'], cfg.get('source_video_processing', {}), cfg.get('finishing_filters', {})
    )
    
    if test_mode:
        print("\n--- 🧪 TEST MODE ENABLED 🧪 ---")
        if cfg.get('test_mode_settings'):
            video_cfg.update(cfg.get('test_mode_settings'))

    routine_elapsed_time, segment_files = 0.0, []

    print("--- 🏋️ Starting Video Assembly 🏋️ ---")
    if source_start_offset > 0: print(f"  > Using source video starting from {source_start_offset:.2f}s.")
    if source_end_limit is not None: print(f"  > Capping source video at {source_end_limit:.2f}s.")
        
    for i, exercise in enumerate(routine):
        segment_number, name, length = i + 1, exercise.get('name', '...').title(), float(exercise.get('length', 0))
        start_time_in_source, end_time_in_source = source_start_offset + routine_elapsed_time, source_start_offset + routine_elapsed_time + length
        
        if segments_to_process and segment_number not in segments_to_process:
            if verbose_mode: print(f"\nSkipping Segment {segment_number}/{len(routine)}: '{name}'")
            routine_elapsed_time += length; continue
        if length <= 0:
            if verbose_mode: print(f"\nSkipping Segment {segment_number}/{len(routine)}: '{name}' (zero length).")
            routine_elapsed_time += length; continue
        if source_end_limit is not None and end_time_in_source > source_end_limit:
            print(f"\n  > WARNING: Segment '{name}' would end past specified end point. Stopping."); break

        output_segment_file = f"temp_segment_{i}.mp4"
        print(f"\nProcessing Segment {segment_number}/{len(routine)}: '{name}' ({length}s)")
        print(f"  > Source time: {start_time_in_source:.2f}s -> {end_time_in_source:.2f}s")
        
        print(f"  > Step 1/3: Checking for timer asset...")
        timer_duration = int(length)
        timer_file = os.path.join(paths_cfg['asset_output_dir'], paths_cfg['timers_subdir'], f'timer_{timer_duration}s.mov')
        use_timer = os.path.exists(timer_file)
        
        ffmpeg_cmd = ['ffmpeg', '-y', '-ss', str(start_time_in_source), '-to', str(end_time_in_source), '-i', source_video_path]
        if use_timer:
            print("    - Found timer asset.")
            ffmpeg_cmd.extend(['-i', timer_file]); timer_input_index = 1
        else:
            print("    - WARNING: Timer not found. Skipping overlay.")

        print("  > Step 2/3: Building FFmpeg command...")
        
        video_filter_chain = "[0:v]setpts=PTS-STARTPTS"
        
        apply_lut, lut_file = source_cfg.get('apply_lut', False), source_cfg.get('lut_file')
        if apply_lut and lut_file and os.path.exists(lut_file):
            print("    - Applying V-Log to Rec.709 transform with provided LUT.")
            lut_path = lut_file.replace('\\', '/').replace(':', '\\:')
            video_filter_chain += (
                f",zscale=rin=full:r=full:matrix=709:p=2020:t=arib-std-b67,"
                f"lut3d=file='{lut_path}',"
                f"zscale=p=709:t=709:m=709:r=limited,"
                f"format=yuv420p"
            )
        
        denoise_cfg = finish_cfg.get('denoise', {})
        if denoise_cfg.get('enabled', False):
            strength, backend = denoise_cfg.get('strength', 1.0), denoise_cfg.get('backend', 'cpu').lower()
            print(f"    - Applying Denoise (Backend: {backend}, Strength: {strength})")
            if backend == 'cuda': video_filter_chain += f",nlmeans_cuda=strength={strength}"
            # --- NEW LOGIC ---
            elif backend == 'opencl':
                # The OpenCL version also uses the 'strength' parameter, which is convenient.
                video_filter_chain += f",nlmeans_opencl=strength={strength}"
            else: video_filter_chain += f",nlmeans=s={strength}"
        
        framing_method = video_cfg.get('framing_method', 'scale').lower()
        framing_backend = video_cfg.get('framing_backend', 'cpu').lower()
        if framing_method == 'crop':
            print("    - Framing method: Cropping to center (CPU).")
            video_filter_chain += f",crop={video_cfg['resolution'].replace('x', ':')}"
        else:
            if framing_backend == 'cuda':
                print(f"    - Framing method: Scaling to fit (GPU: scale_cuda).")
                video_filter_chain += f",scale_cuda={video_cfg['resolution']}"
            else:
                print(f"    - Framing method: Scaling to fit (CPU: scale).")
                video_filter_chain += f",scale={video_cfg['resolution']}"
        
        sharpen_cfg = finish_cfg.get('sharpen', {})
        if sharpen_cfg.get('enabled', False):
            amount, backend = sharpen_cfg.get('luma_amount', 0.5), sharpen_cfg.get('backend', 'cpu').lower()
            print(f"    - Applying Sharpen (Backend: {backend}, Amount: {amount})")
            if backend == 'cuda': video_filter_chain += f",unsharp_cuda=la={amount}"
            else: video_filter_chain += f",unsharp=lx=3:ly=3:la={amount}"
            
        video_filter_chain += ",setsar=1[base];"
        
        filter_complex = video_filter_chain
        last_stream = "[base]"
        if use_timer:
            pos = ring_cfg['position']
            filter_complex += f"[{timer_input_index}:v]scale={ring_cfg['size']}:-1[timer];"
            filter_complex += f"{last_stream}[timer]overlay=x='{pos['x']}':y='{pos['y']}'[v_with_timer];"
            last_stream = "[v_with_timer]"
        
        clean_text, font_path = prepare_text_for_ffmpeg(name, title_cfg['wrap_at_char']), title_cfg['font_file'].replace('\\', '/').replace(':', '\\:')
        filter_complex += (f"{last_stream}drawtext=fontfile='{font_path}':text='{clean_text}':fontsize={title_cfg['font_size']}:fontcolor={title_cfg['font_color']}:box=1:boxcolor={title_cfg['box_color']}:boxborderw={title_cfg['box_border_width']}:x='{title_cfg['position_x']}':y='{title_cfg['position_y']}'[final_v]")
        
        final_cmd_args = ['-filter_complex', filter_complex, '-map', '[final_v]', '-map', '0:a:0?', '-c:v', video_cfg['codec'], '-preset', video_cfg['preset'], '-cq', str(video_cfg['quality']), '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate']]
        if video_cfg.get('audio_channels', 1) == 2: final_cmd_args.extend(['-af', 'pan=stereo|c0=c0|c1=c0'])
        if test_mode and 'framerate' in video_cfg: final_cmd_args.extend(['-r', str(video_cfg['framerate'])])
        
        ffmpeg_cmd.extend(final_cmd_args)
        ffmpeg_cmd.extend(['-t', str(length), output_segment_file])
        
        if verbose_mode:
            print("    - Assembled FFmpeg command:")
            temp_cmd = ffmpeg_cmd.copy()
            temp_cmd[temp_cmd.index('-filter_complex') + 1] = f'"{temp_cmd[temp_cmd.index("-filter_complex") + 1]}"'
            print("      " + " ".join(temp_cmd))
        
        print("  > Step 3/3: Encoding with FFmpeg...")
        encoding_start_time = time.monotonic()
        try:
            if verbose_mode:
                subprocess.run(ffmpeg_cmd, check=True)
            else:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            print(f"    - Done. Segment encoded in {time.monotonic() - encoding_start_time:.2f}s.")
            segment_files.append(output_segment_file)
        except subprocess.CalledProcessError as e:
            print(f"\n--- FATAL: FFmpeg failed on segment for '{name}'. ---")
            if not verbose_mode: print("  > FFmpeg error output (stderr):\n", e.stderr)
            sys.exit(1)

        routine_elapsed_time += length

    if not segment_files:
        print("\nNo segments were created."); sys.exit(0)

    if len(segment_files) == 1:
        print("\n--- 🎞️ Finalizing Single Segment ---")
        try: shutil.move(segment_files[0], output_path); print(f"  > Renamed '{segment_files[0]}' to '{output_path}'.")
        except Exception as e:
            print(f"  > FATAL: Could not move segment file: {e}"); sys.exit(1)
    else:
        print(f"\n--- 🎞️ Concatenating {len(segment_files)} Segments ---")
        concat_file = "concat_list.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            for file in segment_files: f.write(f"file '{Path(file).resolve().as_posix()}'\n")
        
        concat_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', output_path]
        if verbose_mode: print("    - Running concat command:", " ".join(concat_cmd))
            
        concat_start_time = time.monotonic()
        try:
            if verbose_mode: subprocess.run(concat_cmd, check=True)
            else: subprocess.run(concat_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            print(f"  > Concatenation finished in {time.monotonic() - concat_start_time:.2f}s.")
        except subprocess.CalledProcessError as e:
            print(f"  > FATAL: FFmpeg failed during concatenation.")
            if not verbose_mode: print("  > FFmpeg error output (stderr):", e.stderr)
            sys.exit(1)
        try: os.remove(concat_file)
        except OSError: pass

    print("\n--- 🧹 Cleaning Up Temporary Files ---")
    for file in segment_files:
        try: os.remove(file)
        except OSError: pass
    
    print(f"\n✅ Video assembly complete! Final video saved to: {output_path}")
    print(f"   Total time taken: {time.monotonic() - total_start_time:.2f} seconds.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Creates a complete exercise video from a source file and a routine plan.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("routine_path", help="Path to routine YAML file.")
    parser.add_argument("source_video", help="Path to source video file.")
    parser.add_argument("output_video", help="Path for final output video.")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    parser.add_argument("--end", type=float, help="End time in source video (seconds).")
    parser.add_argument("--segments", type=str, help="Comma-separated list of segments to process (e.g., '1,3,5').")
    parser.add_argument("--test", action="store_true", help="Enable test mode for a fast, low-quality preview render.")
    parser.add_argument("--verbose", action="store_true", help="Show the full FFmpeg command and its real-time output.")
    parser.add_argument("--config", type=str, default='config.yaml', help="Path to config file.")
    
    args = parser.parse_args()
    
    segments_to_run = None
    if args.segments:
        try: segments_to_run = [int(s.strip()) for s in args.segments.split(',')]
        except ValueError:
            print("FATAL: Invalid --segments format."); sys.exit(1)

    assemble_video(
        config_path=args.config,
        routine_path=args.routine_path,
        source_video_path=args.source_video,
        output_path=args.output_video,
        segments_to_process=segments_to_run,
        source_start_offset=args.start,
        source_end_limit=args.end,
        test_mode=args.test,
        verbose_mode=args.verbose
    )