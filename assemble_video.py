import os
import sys
import yaml
import textwrap
import subprocess
import argparse
import time
import random
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

def probe_pix_fmt(path):
    """Probes video file to get its pixel format."""
    cmd = ['ffprobe','-v','error','-select_streams','v:0',
           '-show_entries','stream=pix_fmt','-of','default=nw=1:nk=1', path]
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"WARNING: Could not probe pixel format for {path}. Defaulting to yuv420p.")
        return 'yuv420p'

def is_video_file_valid(path: str) -> bool:
    """Checks if a video file is valid and readable by running a silent ffprobe command."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    cmd = ['ffprobe', '-v', 'error', '-i', path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        print("WARNING: ffprobe not found in PATH. Cannot validate segments; will re-render if necessary.")
        return False

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
    verbose_mode: bool = False,
    force_render: bool = False
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
    sfx_cfg = cfg.get('sound_effects', {})

    if test_mode:
        print("\n--- 🧪 TEST MODE ENABLED 🧪 ---")
        if cfg.get('test_mode_settings'):
            video_cfg.update(cfg.get('test_mode_settings'))
    if force_render:
        print("\n--- 💥 FORCED RE-RENDER ENABLED 💥 ---")

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

        # --- REUSE SEGMENT LOGIC ---
        if not force_render and is_video_file_valid(output_segment_file):
            print(f"\nReusing Segment {segment_number}/{len(routine)}: '{name}'")
            segment_files.append(output_segment_file)
            routine_elapsed_time += length
            continue
        # --- END REUSE LOGIC ---

        print(f"\nProcessing Segment {segment_number}/{len(routine)}: '{name}' ({length}s)")
        print(f"  > Source time: {start_time_in_source:.2f}s -> {end_time_in_source:.2f}s")

        print(f"  > Step 1/3: Checking for assets...")
        timer_duration = int(length)
        timer_file = os.path.join(paths_cfg.get('asset_output_dir', '.'), paths_cfg.get('timers_subdir', 'timers'), f'timer_{timer_duration}s.mov')
        use_timer = os.path.exists(timer_file)
        if use_timer: print("    - Found timer asset.")
        else: print("    - WARNING: Timer not found. Skipping overlay.")

        sfx_rule_to_apply, sfx_file = None, None
        sfx_input_index, current_input_index = -1, 1
        if sfx_cfg.get('rules') and sfx_cfg.get('effects'):
            for rule in sfx_cfg['rules']:
                triggers = rule.get('triggers', [])
                if any(trigger == '*' or trigger.lower() in name.lower() for trigger in triggers):
                    if random.random() < rule.get('play_percent', 100) / 100.0:
                        sfx_rule_to_apply = rule
                        break

        ffmpeg_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
                      '-threads', '1', '-filter_threads', '0', '-extra_hw_frames', '8']

        ffmpeg_cmd += ['-ss', str(start_time_in_source), '-to', str(end_time_in_source), '-i', source_video_path]

        if use_timer:
            ffmpeg_cmd.extend(['-i', timer_file]); timer_input_index = current_input_index; current_input_index += 1

        if sfx_rule_to_apply:
            effect_name = sfx_rule_to_apply['effect']
            effect_details = sfx_cfg['effects'].get(effect_name, {})
            sfx_file = effect_details.get('file')
            sfx_layout = effect_details.get('layout', 'stereo')
            if sfx_file and os.path.exists(sfx_file):
                print(f"    - Applying sound effect: '{effect_name}'")
                ffmpeg_cmd.extend(['-channel_layout', sfx_layout, '-i', sfx_file])
                sfx_input_index = current_input_index
                current_input_index += 1
            else:
                print(f"    - WARNING: Sound effect '{effect_name}' file not found. Skipping.")
                sfx_rule_to_apply = None

        print("  > Step 2/3: Building FFmpeg command...")
        target_res = video_cfg['resolution']; W, H = target_res.split('x'); target_res_colon = f"{W}:{H}"
        in_pix = probe_pix_fmt(source_video_path)
        bit_depth = int(video_cfg.get('bit_depth', 8))
        pix_fmt = 'p010le' if bit_depth == 10 else 'yuv420p'
        cpu_download_fmt = 'p010le' if '10' in in_pix else 'nv12'

        if bit_depth == 10 and 'h264' in video_cfg.get('codec', ''):
            print("  > INFO: Switching to HEVC codec for 10-bit output.")
            video_cfg['codec'] = 'hevc_nvenc'

        cpu_filters = [f"[gpu_scaled]hwdownload,format={cpu_download_fmt},setpts=PTS-STARTPTS"]
        if video_cfg.get('framing_method') == 'crop':
            cpu_filters.append(f"crop={W}:{H}:floor((iw-{W})/4)*2:floor((ih-{H})/4)*2")

        apply_lut, lut_files = source_cfg.get('apply_lut', False), source_cfg.get('lut_files', [])
        if apply_lut and isinstance(lut_files, list) and lut_files:
            cpu_filters.append("zscale=rin=full:r=full:matrix=709:p=2020:t=arib-std-b67")
            for lut_file in lut_files:
                if os.path.exists(lut_file):
                    print(f"    - Applying LUT: {os.path.basename(lut_file)}")
                    lut_path = lut_file.replace('\\', '/').replace(':', '\\:')
                    cpu_filters.append(f"lut3d=file='{lut_path}'")
                else:
                    print(f"    - WARNING: LUT file not found, skipping: {lut_file}")
            cpu_filters.append(f"zscale=p=709:t=709:m=709:r=limited,format={pix_fmt}")

        sharpen_cfg = finish_cfg.get('sharpen', {})
        if sharpen_cfg.get('enabled', False):
             cpu_filters.append(f"unsharp=lx=3:ly=3:la={sharpen_cfg.get('luma_amount', 0.5)}")

        last_stream = "[cpu_processed]"
        filter_complex_chains = [f"[0:v]scale_cuda={target_res_colon}:force_original_aspect_ratio=increase[gpu_scaled]", ",".join(cpu_filters) + last_stream]

        if use_timer:
            pos = ring_cfg.get('position', {}); timer_pix_fmt = 'yuva444p10le'
            filter_complex_chains.extend([f"[{timer_input_index}:v]scale={ring_cfg['size']}:-1,format={timer_pix_fmt}[timer]", f"{last_stream}[timer]overlay=x='{pos.get('x', '(W-w)/2')}':y='{pos.get('y', '50')}'[with_timer]"])
            last_stream = "[with_timer]"

        clean_text = prepare_text_for_ffmpeg(name, title_cfg.get('wrap_at_char', 25))
        font_path = title_cfg.get('font_file', '').replace('\\', '/').replace(':', '\\:')
        video_chain_suffix = f"drawtext=fontfile='{font_path}':text='{clean_text}':fontsize={title_cfg.get('font_size',80)}:fontcolor={title_cfg.get('font_color','white')}:box=1:boxcolor={title_cfg.get('box_color','black@0.7')}:boxborderw={title_cfg.get('box_border_width',15)}:x='{title_cfg.get('position_x','(w-text_w)/2')}':y='{title_cfg.get('position_y','h*0.8')}',setsar=1[final_v]"
        filter_complex_chains.append(f"{last_stream}{video_chain_suffix}")

        # --- AUDIO GRAPH LOGIC ---
        audio_map_target = "0:a:0?"
        last_audio_stream = "[0:a:0]"
        is_complex_audio = False

        if sfx_rule_to_apply and sfx_input_index != -1:
            is_complex_audio = True
            start_time = sfx_rule_to_apply.get('start_time', 0.0); delay_ms = 0
            if isinstance(start_time, (int, float)):
                delay_ms = int((length - abs(start_time) if start_time < 0 else start_time) * 1000)
            elif start_time == 'random': delay_ms = random.randint(0, int(length * 1000))

            sfx_details = sfx_cfg['effects'][sfx_rule_to_apply['effect']]
            sfx_vol = sfx_details.get('volume', 1.0) * sfx_cfg.get('master_volume', 1.0)

            mix_chain = (
                f"[0:a:0]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[main_a];"
                f"[{sfx_input_index}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume={sfx_vol:.2f}[sfx_a];"
                f"[sfx_a]adelay={delay_ms}|{delay_ms}[delayed_sfx];"
                f"[main_a][delayed_sfx]amix=inputs=2:duration=first:dropout_transition=1[mixed_a]"
            )
            filter_complex_chains.append(mix_chain)
            last_audio_stream = "[mixed_a]"

        final_audio_filters = []
        if video_cfg.get('audio_channels', 2) == 1:
            final_audio_filters.append("pan=mono|c0=c0")

        if final_audio_filters:
            is_complex_audio = True
            chain_str = ",".join(final_audio_filters)
            filter_complex_chains.append(f"{last_audio_stream}{chain_str}[final_a]")
            audio_map_target = "[final_a]"
        elif is_complex_audio:
            audio_map_target = last_audio_stream

        # --- END AUDIO LOGIC ---

        filter_complex = ";".join(filter_complex_chains)

        final_cmd_args = ['-filter_complex', filter_complex, '-map', '[final_v]', '-map', audio_map_target]
        final_cmd_args.extend(['-c:v', video_cfg['codec'], '-preset', video_cfg['preset'], '-cq', str(video_cfg['quality']), '-pix_fmt', pix_fmt, '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate'], '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709'])

        if video_cfg.get('codec') in ('h264_nvenc', 'hevc_nvenc'):
            final_cmd_args += ['-rc-lookahead', '20', '-spatial_aq', '1', '-temporal_aq', '1', '-aq-strength', '8', '-rc', 'vbr', '-tune', 'hq', '-multipass', 'fullres', '-bf', '3']
            if video_cfg.get('codec') == 'hevc_nvenc': final_cmd_args += ['-profile:v', 'main10' if bit_depth == 10 else 'main']

        ffmpeg_cmd.extend(final_cmd_args); ffmpeg_cmd.extend(['-t', str(length), output_segment_file])

        if verbose_mode:
            print("    - Assembled FFmpeg command:"); print(f"      {' '.join(ffmpeg_cmd)}")

        print("  > Step 3/3: Encoding with FFmpeg...")
        encoding_start_time = time.monotonic()
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
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

        concat_cmd = [ 'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c:v', 'copy', '-c:a', 'aac', '-af', 'aresample=async=1:first_pts=0', output_path ]
        if verbose_mode: print("    - Running concat command:", " ".join(concat_cmd))

        try:
            subprocess.run(concat_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
            print(f"  > Concatenation finished successfully.")
        except subprocess.CalledProcessError as e:
            if not verbose_mode: print("  > FFmpeg error output (stderr):", e.stderr)
            sys.exit(1)
        finally:
             if os.path.exists(concat_file): os.remove(concat_file)

    print("\n--- 🧹 Cleaning Up Temporary Files ---")
    for file in segment_files:
        if os.path.exists(file): os.remove(file)

    total_duration = time.monotonic() - total_start_time
    print(f"\n✅ Video assembly complete! Final video saved to: {output_path}")
    print(f"   Total time taken: {total_duration:.2f} seconds.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser( description="Creates a complete exercise video from a source file and a routine plan.", formatter_class=argparse.ArgumentDefaultsHelpFormatter )
    parser.add_argument("routine_path", help="Path to routine YAML file.")
    parser.add_argument("source_video", help="Path to source video file.")
    parser.add_argument("output_video", help="Path for final output video.")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    parser.add_argument("--end", type=float, help="End time in source video (seconds).")
    parser.add_argument("--segments", type=str, help="Comma-separated list of segments to process (e.g., '1,3,5').")
    parser.add_argument("--test", action="store_true", help="Enable test mode for a fast, low-quality preview render.")
    parser.add_argument("--force-render", action="store_true", help="Force re-rendering of all segments, ignoring existing temp files.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show the full FFmpeg command and its real-time output.")
    parser.add_argument("--config", type=str, default='config.yaml', help="Path to config file.")
    args = parser.parse_args()

    segments_to_run = None
    if args.segments:
        try: segments_to_run = [int(s.strip()) for s in args.segments.split(',')]
        except ValueError: sys.exit("FATAL: Invalid --segments format. Please provide comma-separated numbers (e.g., '1,3,5').")

    assemble_video(
        config_path=args.config,
        routine_path=args.routine_path,
        source_video_path=args.source_video,
        output_path=args.output_video,
        segments_to_process=segments_to_run,
        source_start_offset=args.start,
        source_end_limit=args.end,
        test_mode=args.test,
        verbose_mode=args.verbose,
        force_render=args.force_render
    )