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
import json

# --- Helper Functions ---
def sanitize_text_for_ffmpeg(text: str) -> str:
    """Escapes characters that are special to FFmpeg's drawtext filter."""
    text = text.replace('\\', '\\\\')
    text = text.replace("'", "'\\\\\\''")
    text = text.replace('"', '\\"')
    text = text.replace('%', '\\%')
    text = text.replace(':', '\\:')
    return text

def escape_ffmpeg_path(path_str: str) -> str:
    """Correctly escapes a path for use in an FFmpeg filtergraph on Windows."""
    path_str = path_str.replace('\\', '/')
    return path_str.replace(':', '\\:', 1)

def prepare_text_for_ffmpeg(text: str, line_width: int = 25) -> str:
    """Wraps text and sanitizes it for the drawtext filter."""
    wrapped_lines = textwrap.wrap(text, width=line_width, break_long_words=True, replace_whitespace=True)
    wrapped_text = "\n".join(wrapped_lines)
    return sanitize_text_for_ffmpeg(wrapped_text)

def probe_media_format(path: str, stream_specifier: str = 'v:0'):
    """Probes a media file to get format information (e.g., pix_fmt, duration)."""
    cmd = ['ffprobe', '-v', 'error', '-select_streams', stream_specifier,
           '-show_entries', 'stream=pix_fmt,duration', '-of', 'json', str(path)]
    try:
        result = subprocess.check_output(cmd, text=True, encoding='utf-8')
        data = json.loads(result)
        return data['streams'][0] if data.get('streams') else {}
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        print(f"WARNING: Could not probe media format for {path}.")
        return {}

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
    config_path: str, routine_path: str, source_video_path: str, output_path: str,
    segments_to_process: list[int] | None = None, source_start_offset: float = 0.0,
    source_end_limit: float | None = None, test_mode: bool = False,
    verbose_mode: bool = False, force_render: bool = False
):
    total_start_time = time.monotonic()

    try:
        with open(config_path, 'r', encoding='utf-8') as f: cfg = yaml.safe_load(f)
    except FileNotFoundError: sys.exit(f"FATAL: Config file not found at '{config_path}'")
    try:
        with open(routine_path, 'r', encoding='utf-8') as f: routine = yaml.safe_load(f)
    except FileNotFoundError: sys.exit(f"FATAL: Routine file not found at '{routine_path}'")
    if not os.path.exists(source_video_path): sys.exit(f"FATAL: Source video not found at '{source_video_path}'")

    paths_cfg, video_cfg = cfg.get('paths', {}), cfg.get('video_output', {}).copy()
    title_cfg, ring_cfg = cfg.get('text_overlays', {}).get('exercise_name', {}), cfg.get('progress_ring', {})
    source_cfg, finish_cfg = cfg.get('source_video_processing', {}), cfg.get('finishing_filters', {})
    sfx_cfg = cfg.get('sound_effects', {})
    bgm_cfg = cfg.get('background_music', {})

    if test_mode:
        print("\n--- 🧪 TEST MODE ENABLED 🧪 ---")
        if cfg.get('test_mode_settings'): video_cfg.update(cfg.get('test_mode_settings'))
    if force_render: print("\n--- 💥 FORCED RE-RENDER ENABLED 💥 ---")

    bgm_enabled = bgm_cfg.get('enabled', False)
    music_files = []
    if bgm_enabled:
        music_folder_path = bgm_cfg.get('music_folder')
        if music_folder_path and os.path.isdir(music_folder_path):
            music_folder = Path(music_folder_path)
            extensions = ('*.mp3', '*.wav', '*.flac', '*.m4a', '*.aac')
            print("  > Searching for music files recursively...")
            for ext in extensions: music_files.extend(music_folder.rglob(ext))
        if not music_files:
            print("  > WARNING: Background music enabled, but no music files found. Disabling."); bgm_enabled = False
        else: print(f"    - Found {len(music_files)} music files.")
    current_bgm_track = {'path': None, 'elapsed': 0.0}

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
            continue
        if source_end_limit is not None and start_time_in_source >= source_end_limit:
            print(f"\n  > WARNING: Reached specified source end limit. Stopping assembly."); break

        output_segment_file = f"temp_segment_{i}.mp4"

        if not force_render and is_video_file_valid(output_segment_file):
            print(f"\nReusing Segment {segment_number}/{len(routine)}: '{name}'")
            segment_files.append(output_segment_file); routine_elapsed_time += length; continue

        print(f"\nProcessing Segment {segment_number}/{len(routine)}: '{name}' ({length}s)")
        print(f"  > Step 1/3: Checking for assets...")
        timer_file = os.path.join(paths_cfg.get('asset_output_dir', '.'), paths_cfg.get('timers_subdir', 'timers'), f'timer_{int(length)}s.mov')
        use_timer = os.path.exists(timer_file)
        if use_timer: print("    - Found timer asset.")
        else: print("    - WARNING: Timer not found. Skipping overlay.")

        sfx_rule_to_apply = next((rule for rule in sfx_cfg.get('rules', []) if any(t == '*' or t.lower() in name.lower() for t in rule.get('triggers', [])) and random.random() < rule.get('play_percent', 100) / 100.0), None)

        bgm_track_for_segment, bgm_mode, bgm_start_offset, bgm_input_index = None, 'continue', 0.0, -1
        if bgm_enabled:
            rule_matched = next((rule for rule in bgm_cfg.get('rules', []) if any(t.lower() in name.lower() for t in rule.get('triggers',[]))), None)
            if rule_matched and Path(rule_matched['file']).exists():
                bgm_track_for_segment, bgm_mode = Path(rule_matched['file']), rule_matched.get('mode', 'loop')
                if bgm_track_for_segment != current_bgm_track.get('path'): current_bgm_track = {'path': bgm_track_for_segment, 'elapsed': 0.0}
            elif current_bgm_track['path'] and current_bgm_track['path'].exists(): bgm_track_for_segment = current_bgm_track['path']
            elif music_files:
                bgm_track_for_segment = random.choice(music_files)
                current_bgm_track = {'path': bgm_track_for_segment, 'elapsed': 0.0}
            bgm_start_offset = current_bgm_track.get('elapsed', 0.0)

        ffmpeg_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-threads', '1', '-filter_threads', '0']
        
        ffmpeg_cmd += ['-channel_layout', 'mono', '-ss', str(start_time_in_source), '-to', str(end_time_in_source), '-i', source_video_path]
        
        current_input_index = 1; timer_input_index, sfx_input_index = -1, -1
        if use_timer:
            ffmpeg_cmd.extend(['-i', timer_file]); timer_input_index = current_input_index; current_input_index += 1
        if sfx_rule_to_apply:
            effect_details = sfx_cfg['effects'][sfx_rule_to_apply['effect']]
            if Path(effect_details['file']).exists():
                ffmpeg_cmd.extend(['-channel_layout', effect_details.get('layout', 'stereo'), '-i', effect_details['file']])
                sfx_input_index = current_input_index; current_input_index += 1
            else: sfx_rule_to_apply = None
        if bgm_track_for_segment:
            print(f"    - Applying music: {bgm_track_for_segment.name} (Mode: {bgm_mode})")
            ffmpeg_cmd.extend(['-channel_layout', 'stereo', '-i', str(bgm_track_for_segment)])
            bgm_input_index = current_input_index; current_input_index += 1

        print("  > Step 2/3: Building FFmpeg command...")
        target_res = video_cfg['resolution']; W, H = target_res.split('x');
        in_pix_fmt = probe_media_format(source_video_path, 'v:0').get('pix_fmt', 'yuv420p')
        bit_depth = int(video_cfg.get('bit_depth', 8))
        pix_fmt = 'p010le' if bit_depth == 10 else 'yuv420p'
        cpu_download_fmt = 'p010le' if '10' in in_pix_fmt else 'nv12'
        if bit_depth == 10 and 'h264' in video_cfg.get('codec', ''): video_cfg['codec'] = 'hevc_nvenc'

        cpu_filters = [f"[gpu_scaled]hwdownload,format={cpu_download_fmt},setpts=PTS-STARTPTS"]
        if video_cfg.get('framing_method') == 'crop': cpu_filters.append(f"crop={W}:{H}:floor((iw-{W})/4)*2:floor((ih-{H})/4)*2")
        if source_cfg.get('apply_lut', False) and source_cfg.get('lut_files'):
            cpu_filters.append("zscale=rin=full:r=full:matrix=709:p=2020:t=arib-std-b67")
            for lut_file in source_cfg['lut_files']:
                if os.path.exists(lut_file): cpu_filters.append(f"lut3d=file='{escape_ffmpeg_path(lut_file)}'")
            cpu_filters.append(f"zscale=p=709:t=709:m=709:r=limited,format={pix_fmt}")
        if finish_cfg.get('sharpen', {}).get('enabled', False):
             cpu_filters.append(f"unsharp=lx=3:ly=3:la={finish_cfg['sharpen'].get('luma_amount', 0.5)}")

        last_stream = "[cpu_processed]"
        filter_complex_chains = [f"[0:v]scale_cuda={W}:{H}:force_original_aspect_ratio=increase[gpu_scaled]", ",".join(cpu_filters) + last_stream]
        if use_timer:
            pos = ring_cfg.get('position', {})
            filter_complex_chains.extend([f"[{timer_input_index}:v]scale={ring_cfg['size']}:-1,format=yuva444p10le[timer]", f"{last_stream}[timer]overlay=x='{pos.get('x', '(W-w)/2')}':y='{pos.get('y', '50')}'[with_timer]"])
            last_stream = "[with_timer]"
        font_path = escape_ffmpeg_path(title_cfg.get('font_file', ''))
        video_chain_suffix = f"drawtext=fontfile='{font_path}':text='{prepare_text_for_ffmpeg(name, title_cfg.get('wrap_at_char', 25))}':fontsize={title_cfg.get('font_size',80)}:fontcolor={title_cfg.get('font_color','white')}:box=1:boxcolor={title_cfg.get('box_color','black@0.7')}:boxborderw={title_cfg.get('box_border_width',15)}:x='{title_cfg.get('position_x','(w-text_w)/2')}':y='{title_cfg.get('position_y','h*0.8')}',setsar=1[final_v]"
        filter_complex_chains.append(f"{last_stream}{video_chain_suffix}")

        audio_streams_to_mix, audio_map_target = [], "0:a:0?"
        filter_complex_chains.append(f"[0:a:0]aformat=fltp:48000:stereo,asetpts=PTS-STARTPTS[main_a]")
        
        # --- DEFINITIVE FIX FOR MISSING SOUND EFFECTS ---
        sfx_stream_for_ducking, sfx_stream_for_mix, bgm_stream = None, None, None

        if sfx_input_index != -1 and sfx_rule_to_apply:
            start_time = sfx_rule_to_apply.get('start_time', 0.0); delay_ms = int((length - abs(start_time) if start_time < 0 else start_time) * 1000)
            sfx_vol = sfx_cfg['effects'][sfx_rule_to_apply['effect']].get('volume', 1.0) * sfx_cfg.get('master_volume', 1.0)
            
            sfx_chain = f"[{sfx_input_index}:a]aformat=fltp:48000:stereo,volume={sfx_vol:.2f}[sfx_base];[sfx_base]adelay={delay_ms}|{delay_ms}[sfx_delayed]"
            filter_complex_chains.append(sfx_chain)

            # Split the SFX stream so it can be used for both ducking and final mix
            filter_complex_chains.append("[sfx_delayed]asplit=2[sfx_for_ducking][sfx_for_mix]")
            sfx_stream_for_ducking = "[sfx_for_ducking]"
            sfx_stream_for_mix = "[sfx_for_mix]"

        if bgm_input_index != -1:
            bgm_vol = bgm_cfg.get('master_volume', 0.15)
            bgm_chain_parts = [f"[{bgm_input_index}:a]aformat=fltp:48000:stereo,volume={bgm_vol:.2f},asetpts=PTS-STARTPTS"]
            if bgm_start_offset > 0: bgm_chain_parts.append(f"atrim=start={bgm_start_offset:.3f}")
            if bgm_mode == 'loop': bgm_chain_parts.append("aloop=loop=-1:size=2e+09")
            bgm_chain_parts.append(f"atrim=duration={length}")
            filter_complex_chains.append(",".join(bgm_chain_parts) + "[bgm_final]")
            bgm_stream = "[bgm_final]"

        # Now decide how to mix
        main_audio_stream = "[main_a]"
        audio_streams_to_mix.append(main_audio_stream)

        if sfx_stream_for_ducking and bgm_stream and bgm_cfg.get('ducking_enabled', False):
            duck_vol = bgm_cfg.get('ducking_volume', 0.2)
            filter_complex_chains.append(f"{bgm_stream}{sfx_stream_for_ducking}sidechaincompress=threshold=0.01:ratio=10:level_sc={duck_vol}[bgm_ducked]")
            audio_streams_to_mix.append("[bgm_ducked]") # Use the ducked version
        elif bgm_stream:
            audio_streams_to_mix.append(bgm_stream) # Use the un-ducked version
        
        if sfx_stream_for_mix:
            audio_streams_to_mix.append(sfx_stream_for_mix) # Always add the SFX to the final mix

        if len(audio_streams_to_mix) > 1:
            filter_complex_chains.append(f"{''.join(audio_streams_to_mix)}amix=inputs={len(audio_streams_to_mix)}:duration=first[final_a]")
            audio_map_target = "[final_a]"
        else:
            audio_map_target = main_audio_stream
        # --- END OF FIX ---

        filter_complex = ";".join(filter_complex_chains)
        final_cmd_args = ['-filter_complex', filter_complex, '-map', '[final_v]', '-map', audio_map_target]
        final_cmd_args.extend(['-c:v', video_cfg['codec'], '-preset', video_cfg['preset'], '-cq', str(video_cfg['quality']), '-pix_fmt', pix_fmt, '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate'], '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709'])
        if video_cfg.get('codec') in ('h264_nvenc', 'hevc_nvenc'):
            final_cmd_args += ['-rc-lookahead', '20', '-spatial_aq', '1', '-temporal_aq', '1', '-aq-strength', '8', '-rc', 'vbr', '-tune', 'hq', '-multipass', 'fullres', '-bf', '3']
            if video_cfg.get('codec') == 'hevc_nvenc': final_cmd_args += ['-profile:v', 'main10' if bit_depth == 10 else 'main']
        ffmpeg_cmd.extend(final_cmd_args); ffmpeg_cmd.extend(['-t', str(length), output_segment_file])

        if verbose_mode: print("    - Assembled FFmpeg command:"); print(f"      {' '.join(ffmpeg_cmd)}")
        print("  > Step 3/3: Encoding with FFmpeg...")
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
            segment_files.append(output_segment_file)
        except subprocess.CalledProcessError as e: sys.exit(f"\n--- FATAL: FFmpeg failed on segment for '{name}'. ---\n{e.stderr}")
        routine_elapsed_time += length
        if bgm_enabled and bgm_mode == 'continue' and current_bgm_track['path']: current_bgm_track['elapsed'] += length

    if not segment_files: sys.exit("\nNo segments were created.")
    total_render_duration = sum(float(probe_media_format(s, 'v:0').get('duration',0)) for s in segment_files)

    if segments_to_process and len(segments_to_process) == 1 and len(segment_files) == 1:
        print("\n--- 🎞️ Finalizing Single Segment ---"); shutil.move(segment_files[0], output_path);
    else:
        print(f"\n--- 🎞️ Concatenating {len(segment_files)} Segments ---")
        concat_file = "concat_list.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            for file in segment_files: f.write(f"file '{Path(file).resolve().as_posix()}'\n")
        audio_filter_chain = ["aresample=async=1:first_pts=0"]
        fade_duration = bgm_cfg.get('fade_duration', 0)
        if bgm_enabled and fade_duration > 0 and total_render_duration > fade_duration * 2:
            fade_out_start = total_render_duration - fade_duration
            audio_filter_chain.append(f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_out_start:.2f}:d={fade_duration}")
        concat_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c:v', 'copy', '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate'], '-af', ",".join(audio_filter_chain), output_path]

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
        config_path=args.config, routine_path=args.routine_path, source_video_path=args.source_video,
        output_path=args.output_video, segments_to_process=segments_to_run,
        source_start_offset=args.start, source_end_limit=args.end,
        test_mode=args.test, verbose_mode=args.verbose, force_render=args.force_render
    )