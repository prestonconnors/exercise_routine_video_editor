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
        sys.exit(f"FATAL: Config file not found at '{config_path}'")
    try:
        with open(routine_path, 'r') as f: routine = yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(f"FATAL: Routine file not found at '{routine_path}'")
    if not os.path.exists(source_video_path):
        sys.exit(f"FATAL: Source video not found at '{source_video_path}'")

    paths_cfg = cfg.get('paths', {})
    video_cfg = cfg.get('video_output', {}).copy()
    title_cfg = cfg.get('text_overlays', {}).get('exercise_name', {})
    ring_cfg = cfg.get('progress_ring', {})
    source_cfg = cfg.get('source_video_processing', {})
    finish_cfg = cfg.get('finishing_filters', {})
    
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
        timer_file = os.path.join(paths_cfg.get('asset_output_dir', '.'), paths_cfg.get('timers_subdir', 'timers'), f'timer_{timer_duration}s.mov')
        use_timer = os.path.exists(timer_file)
        
        ffmpeg_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda']
        if finish_cfg.get('denoise', {}).get('enabled', False) and finish_cfg.get('denoise', {}).get('backend', 'cpu').lower() == 'opencl':
            ocl_device = cfg.get('opencl', {}).get('device', '0.0')
            ffmpeg_cmd += ['-init_hw_device', f'opencl=ocl:{ocl_device}', '-filter_hw_device', 'ocl']
            
        ffmpeg_cmd += ['-ss', str(start_time_in_source), '-to', str(end_time_in_source), '-i', source_video_path]
        if use_timer:
            print("    - Found timer asset.")
            ffmpeg_cmd.extend(['-i', timer_file]); timer_input_index = 1
        else:
            print("    - WARNING: Timer not found. Skipping overlay.")

        print("  > Step 2/3: Building FFmpeg command...")
        
        cpu_filters = ["[0:v]hwdownload,format=p010le,setpts=PTS-STARTPTS"]
        
        apply_lut, lut_file = source_cfg.get('apply_lut', False), source_cfg.get('lut_file')
        if apply_lut and lut_file and os.path.exists(lut_file):
            print("    - Applying LUT and Color Transform (CPU).")
            lut_path = lut_file.replace('\\', '/').replace(':', '\\:')
            cpu_filters.extend([f"zscale=rin=full:r=full:matrix=709:p=2020:t=arib-std-b67", f"lut3d=file='{lut_path}'", f"zscale=p=709:t=709:m=709:r=limited,format=yuv420p"])
        
        framing_method = video_cfg.get('framing_method', 'scale').lower()
        if framing_method == 'crop':
            print("    - Framing: Cropping to center (CPU).")
            cpu_filters.append(f"crop={video_cfg['resolution'].replace('x',':')}")
        
        sharpen_cfg = finish_cfg.get('sharpen', {})
        if sharpen_cfg.get('enabled', False) and sharpen_cfg.get('backend', 'cpu').lower() == 'cpu':
            amount = sharpen_cfg.get('luma_amount', 0.5)
            print(f"    - Applying Sharpen (CPU).")
            cpu_filters.append(f"unsharp=lx=3:ly=3:la={amount}")

        base_filter_chain = ",".join(cpu_filters)
        last_stream = "[cpu_processed]"
        filter_complex_chains = [base_filter_chain + last_stream]

        gpu_filters_used, gpu_filters = False, []
        denoise_cfg = finish_cfg.get('denoise', {})
        if denoise_cfg.get('enabled', False) and denoise_cfg.get('backend', 'cpu').lower() == 'opencl':
            strength = denoise_cfg.get('strength', 1.0)
            print(f"    - Applying Denoise (GPU: OpenCL).")
            ocl_chain = f"{last_stream}format=yuv420p,hwupload,nlmeans_opencl=s={strength},hwdownload,format=yuv420p[ocl_done]"
            filter_complex_chains.append(ocl_chain)
            last_stream = "[ocl_done]"
            
        if framing_method != 'crop' and video_cfg.get('framing_backend', 'cpu').lower() == 'cuda':
            gpu_filters_used = True
            print(f"    - Framing: Scaling to fit (GPU).")
            gpu_filters.append(f"scale_cuda={video_cfg['resolution']}")
        
        if gpu_filters_used:
            gpu_chain = f"{last_stream}format=nv12,hwupload_cuda,{','.join(gpu_filters)}[gpu_processed]"
            filter_complex_chains.append(gpu_chain)
            last_stream = "[gpu_processed]"

        if use_timer:
            pos = ring_cfg.get('position', {})
            filter_complex_chains.append(f"[{timer_input_index}:v]scale={ring_cfg['size']}:-1,format=yuva420p[timer]")
            filter_complex_chains.append(f"{last_stream}[timer]overlay=x='{pos.get('x', '(W-w)/2')}':y='{pos.get('y', '50')}'[with_timer]")
            last_stream = "[with_timer]"
        
        final_chain_parts = []
        if last_stream == "[gpu_processed]":
            final_chain_parts.append("hwdownload,format=yuv420p")
            
        clean_text = prepare_text_for_ffmpeg(name, title_cfg.get('wrap_at_char', 25))
        font_path = title_cfg.get('font_file', '').replace('\\', '/').replace(':', '\\:')
        final_chain_parts.append(f"drawtext=fontfile='{font_path}':text='{clean_text}':fontsize={title_cfg.get('font_size',80)}:fontcolor={title_cfg.get('font_color','white')}:box=1:boxcolor={title_cfg.get('box_color','black@0.7')}:boxborderw={title_cfg.get('box_border_width',15)}:x='{title_cfg.get('position_x','(w-text_w)/2')}':y='{title_cfg.get('position_y','h*0.8')}'")
        final_chain_parts.append("setsar=1[final_v]")
        
        final_filters_str = ",".join(final_chain_parts)
        final_chain = f"{last_stream}{final_filters_str}"
        filter_complex_chains.append(final_chain)
        
        filter_complex = ";".join(filter_complex_chains)
        
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
            if verbose_mode: subprocess.run(ffmpeg_cmd, check=True)
            else: subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            print(f"    - Done. Segment encoded in {time.monotonic() - encoding_start_time:.2f}s.")
            segment_files.append(output_segment_file)
        except subprocess.CalledProcessError as e:
            print(f"\n--- FATAL: FFmpeg failed on segment for '{name}'. ---")
            if not verbose_mode: print("  > FFmpeg error output (stderr):\n", e.stderr)
            sys.exit(1)

        routine_elapsed_time += length

    if not segment_files:
        sys.exit("\nNo segments were created.")

    if len(segment_files) == 1:
        print("\n--- 🎞️ Finalizing Single Segment ---")
        try: shutil.move(segment_files[0], output_path); print(f"  > Renamed '{segment_files[0]}' to '{output_path}'.")
        except Exception as e:
            sys.exit(f"  > FATAL: Could not move segment file: {e}")
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
    cleanup_files = segment_files
    for file in cleanup_files:
        try: os.remove(file)
        except OSError: pass
    
    total_duration = time.monotonic() - total_start_time
    print(f"\n✅ Video assembly complete! Final video saved to: {output_path}")
    print(f"   Total time taken: {total_duration:.2f} seconds.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Creates a complete exercise video from a source file and a routine plan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument("routine_path", help="Path to routine YAML file.")
    parser.add_argument("source_video", help="Path to source video file.")
    parser.add_argument("output_video", help="Path for final output video.")
    
    parser.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    parser.add_argument("--end", type=float, help="End time in source video (seconds).")
    parser.add_argument("--segments", type=str, help="Comma-separated list of segments to process (e.g., '1,3,5').")
    
    parser.add_argument("--test", action="store_true", help="Enable test mode for a fast, low-quality preview render.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show the full FFmpeg command and its real-time output.")
    parser.add_argument("--config", type=str, default='config.yaml', help="Path to config file.")
    
    args = parser.parse_args()
    
    segments_to_run = None
    if args.segments:
        try:
            segments_to_run = [int(s.strip()) for s in args.segments.split(',')]
        except ValueError:
            sys.exit("FATAL: Invalid --segments format. Please provide comma-separated numbers (e.g., '1,3,5').")

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