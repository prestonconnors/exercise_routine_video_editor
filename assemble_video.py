import os
import sys
import re
import yaml
import textwrap
import subprocess
import argparse
import time
import random
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import json

# Module-level caches (thread-safe for our usage: writes are idempotent).
_PROBE_PIX_FMT_CACHE: dict[str, str] = {}
_PROBE_LOCK = threading.Lock()
_MANIFEST_PATH = ".cache/segments_manifest.json"
_MANIFEST_LOCK = threading.Lock()

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
    """Probes video file to get its pixel format. Cached per path."""
    cached = _PROBE_PIX_FMT_CACHE.get(path)
    if cached is not None:
        return cached
    cmd = ['ffprobe','-v','error','-select_streams','v:0',
           '-show_entries','stream=pix_fmt','-of','default=nw=1:nk=1', path]
    try:
        result = subprocess.check_output(cmd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"WARNING: Could not probe pixel format for {path}. Defaulting to yuv420p.")
        result = 'yuv420p'
    with _PROBE_LOCK:
        _PROBE_PIX_FMT_CACHE[path] = result
    return result


def _load_manifest() -> dict:
    if not os.path.exists(_MANIFEST_PATH):
        return {}
    try:
        with open(_MANIFEST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _update_manifest_entry(key: str, value: str) -> None:
    with _MANIFEST_LOCK:
        manifest = _load_manifest()
        manifest[key] = value
        Path(_MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(_MANIFEST_PATH, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, sort_keys=True)


def _prune_manifest(active_paths: set[str]) -> None:
    """Drop manifest entries whose temp files no longer exist or are not in `active_paths`.

    Prevents the manifest from accumulating stale keys (e.g. after a
    single-segment finalize that moves the temp into the output path).
    """
    with _MANIFEST_LOCK:
        manifest = _load_manifest()
        before = len(manifest)
        pruned = {k: v for k, v in manifest.items()
                  if k in active_paths and os.path.exists(k) and os.path.getsize(k) > 0}
        if len(pruned) != before:
            Path(_MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(_MANIFEST_PATH, 'w', encoding='utf-8') as f:
                json.dump(pruned, f, indent=2, sort_keys=True)


def _segment_fingerprint(payload: dict) -> str:
    """Stable hash over everything that affects a segment's rendered output."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()

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

def optimize_final_audio(config_path: str, video_file_path: str, verbose: bool = False):
    """
    Performs a two-pass loudness normalization on the final video file.
    Crucially, this uses `-c:v copy` on the second pass to avoid re-encoding video.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"WARNING: Config file not found at '{config_path}', skipping final audio optimization.")
        return

    opt_cfg = cfg.get('audio_optimization', {})
    norm_cfg = opt_cfg.get('loudness_normalization', {})

    if not opt_cfg.get('enabled') or not norm_cfg.get('enabled'):
        print("\n--- Final audio optimization disabled in config. Skipping. ---")
        return

    print("\n--- 🔊 Performing Final Audio Optimization ---")
    
    # --- PASS 1: ANALYSIS ---
    print("  > Step 1/2: Analyzing audio loudness...")
    target_i = norm_cfg.get('target_i', -16)
    target_lra = norm_cfg.get('target_lra', 11)
    target_tp = norm_cfg.get('target_tp', -1.5)

    pass1_cmd = [
        'ffmpeg', '-i', video_file_path, '-af',
        f'loudnorm=I={target_i}:LRA={target_lra}:tp={target_tp}:print_format=json',
        '-f', 'null', '-'
    ]
    
    try:
        # We need to capture stderr because ffmpeg writes loudnorm stats there
        result = subprocess.run(pass1_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        print("\n--- FATAL: FFmpeg failed during audio analysis pass. ---")
        print("  > FFmpeg error output (stderr):\n", e.stderr)
        sys.exit(1)
        
    # Extract the loudnorm JSON object from the messy stderr. We can't just
    # slice from first '{' to last '}' because other filters may emit braces;
    # find a brace block that contains the 'input_i' key instead.
    json_match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr, re.DOTALL)
    json_str = json_match.group(0) if json_match else ""

    if not json_str:
        print("\n--- FATAL: Could not find loudnorm JSON data in FFmpeg output. ---")
        print("  > FFmpeg output:\n", result.stderr)
        sys.exit(1)
        
    try:
        loudnorm_stats = json.loads(json_str)
        if verbose: print("    - Analysis complete. Stats:", loudnorm_stats)
    except json.JSONDecodeError:
        print("\n--- FATAL: Failed to parse loudnorm JSON data. ---")
        print("  > Raw string for parsing:\n", json_str)
        sys.exit(1)

    # --- PASS 2: APPLYING NORMALIZATION ---
    print("  > Step 2/2: Applying normalization (video stream will be copied)...")
    
    # Prepare a temporary output path to avoid read/write conflicts
    original_path = Path(video_file_path)
    temp_output_path = original_path.with_name(f"{original_path.stem}_temp_normalized{original_path.suffix}")

    pass2_cmd = [
        'ffmpeg', '-y', '-i', video_file_path, '-af',
        (f"loudnorm=I={target_i}:LRA={target_lra}:tp={target_tp}:"
         f"measured_i={loudnorm_stats['input_i']}:"
         f"measured_lra={loudnorm_stats['input_lra']}:"
         f"measured_tp={loudnorm_stats['input_tp']}:"
         f"measured_thresh={loudnorm_stats['input_thresh']}:"
         f"offset={loudnorm_stats['target_offset']}"),
        '-c:v', 'copy',  # <-- This is the magic part!
        '-c:a', cfg.get('video_output', {}).get('audio_codec', 'aac'),
        '-b:a', cfg.get('video_output', {}).get('audio_bitrate', '192k'),
        str(temp_output_path)
    ]
    
    try:
        subprocess.run(pass2_cmd, check=True, capture_output=not verbose, text=True, encoding='utf-8')
        print(f"    - Normalization successful.")
    except subprocess.CalledProcessError as e:
        print("\n--- FATAL: FFmpeg failed during audio normalization pass. ---")
        if not verbose: print("  > FFmpeg error output (stderr):\n", e.stderr)
        sys.exit(1)
        
    # Replace original with the new normalized file
    os.remove(video_file_path)
    shutil.move(str(temp_output_path), video_file_path)
    print("  > Final audio optimized successfully.")

# --- Per-Segment Renderer (parallel-safe) ---
def _render_segment(task: dict, ctx: dict, verbose_mode: bool) -> list[str]:
    """Render one segment to its temp_segment_<i>.mp4 file.

    `task` carries fully resolved per-segment data (no shared mutation).
    `ctx`  carries shared, read-only config dicts plus pre-baked LUT path(s).

    Returns a list of log strings; the caller prints them when the future
    completes so each segment's logs stay grouped together.
    """
    logs: list[str] = []
    def log(msg: str) -> None:
        logs.append(msg)

    cfg = ctx['cfg']
    paths_cfg = ctx['paths_cfg']
    video_cfg = dict(ctx['video_cfg'])  # per-task copy in case codec switches
    title_cfg = ctx['title_cfg']
    ring_cfg = ctx['ring_cfg']
    source_cfg = ctx['source_cfg']
    finish_cfg = ctx['finish_cfg']
    sfx_cfg = ctx['sfx_cfg']
    bgm_cfg = ctx['bgm_cfg']
    effective_luts = ctx.get('effective_luts') or []

    name = task['name']
    length = task['length']
    output_segment_file = task['output']
    final_video_input_path = task['video_input_path']
    final_video_input_args = task['video_input_args']
    final_audio_input_path = task['audio_input_path']
    final_audio_input_args = task['audio_input_args']
    timer_file = task['timer_file']
    use_timer = task['use_timer']
    use_bgm = task['use_bgm']
    bgm_offset = task['bgm_offset']
    background_music_path = task['background_music_path']
    sfx_rule_to_apply = task['sfx_rule_to_apply']
    sfx_delay_ms = task['sfx_delay_ms']

    log(f"\nProcessing Segment {task['segment_number']}/{task['total_segments']}: '{name}' ({length}s)")
    if task.get('replaced_video'):
        log(f"  > Replacing video with: {os.path.basename(final_video_input_path)}")
    if task.get('replaced_audio'):
        log(f"  > Replacing audio with: {os.path.basename(final_audio_input_path)}")
    log(f"  > Source time: {task['start_time_in_source']:.2f}s -> {task['end_time_in_source']:.2f}s")
    log("  > Step 1/3: Checking for assets...")
    if use_timer:
        log("    - Found timer asset.")
    else:
        log("    - WARNING: Timer not found. Skipping overlay.")

    # NOTE: '-threads 1 -filter_threads 0' previously forced single-threaded CPU
    # filtering. CPU-side lut3d/zscale/unsharp scale across cores; let FFmpeg
    # pick its own thread count.
    ffmpeg_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
                  '-extra_hw_frames', '8']

    current_input_index = 0
    ffmpeg_cmd.extend(final_video_input_args)
    ffmpeg_cmd.extend(['-i', final_video_input_path])
    video_stream_spec = f"[{current_input_index}:v]"
    video_input_stream_index = current_input_index
    current_input_index += 1

    if final_audio_input_path == final_video_input_path and final_audio_input_args == final_video_input_args:
        audio_stream_spec = f"[{video_input_stream_index}:a:0]"
    else:
        ffmpeg_cmd.extend(final_audio_input_args)
        ffmpeg_cmd.extend(['-i', final_audio_input_path])
        audio_stream_spec = f"[{current_input_index}:a:0]"
        current_input_index += 1

    timer_input_index = sfx_input_index = bgm_input_index = -1

    if use_timer:
        ffmpeg_cmd.extend(['-i', timer_file])
        timer_input_index = current_input_index
        current_input_index += 1

    if use_bgm:
        log("    - Found background music.")
        ffmpeg_cmd.extend(['-ss', str(bgm_offset), '-i', background_music_path])
        bgm_input_index = current_input_index
        current_input_index += 1

    if sfx_rule_to_apply:
        effect_name = sfx_rule_to_apply['effect']
        effect_details = sfx_cfg['effects'].get(effect_name, {})
        sfx_path = effect_details.get('file')
        sfx_layout = effect_details.get('layout', 'stereo')
        log(f"    - Applying sound effect: '{effect_name}'")
        ffmpeg_cmd.extend(['-channel_layout', sfx_layout, '-i', sfx_path])
        sfx_input_index = current_input_index
        current_input_index += 1

    log("  > Step 2/3: Building FFmpeg command...")
    target_res = video_cfg['resolution']
    W, H = target_res.split('x')
    target_res_colon = f"{W}:{H}"
    in_pix = probe_pix_fmt(final_video_input_path)
    bit_depth = int(video_cfg.get('bit_depth', 8))
    pix_fmt = 'p010le' if bit_depth == 10 else 'yuv420p'
    cpu_download_fmt = 'p010le' if '10' in in_pix else 'nv12'

    if bit_depth == 10 and 'h264' in video_cfg.get('codec', ''):
        video_cfg['codec'] = 'hevc_nvenc'

    filter_complex_chains: list[str] = []

    cpu_filters = [f"[gpu_scaled]hwdownload,format={cpu_download_fmt},setpts=PTS-STARTPTS"]
    if video_cfg.get('framing_method') == 'crop':
        cpu_filters.append(f"crop={W}:{H}:floor((iw-{W})/4)*2:floor((ih-{H})/4)*2")
    sharpen_cfg = finish_cfg.get('sharpen', {})
    if effective_luts:
        # Skip the BT.2020/HLG roundtrip the original code did -- a no-op for
        # V-Log -> Rec.709 LUT chains and an expensive zscale pair.
        cpu_filters.append("zscale=rin=tv:r=full")
        for lut_file in effective_luts:
            log(f"    - Applying LUT: {os.path.basename(lut_file)}")
            lut_path = lut_file.replace('\\', '/').replace(':', '\\:')
            cpu_filters.append(f"lut3d=file='{lut_path}':interp=tetrahedral")
        cpu_filters.append(f"zscale=rin=full:r=limited,format={pix_fmt}")
    if sharpen_cfg.get('enabled', False):
        cpu_filters.append(f"unsharp=lx=3:ly=3:la={sharpen_cfg.get('luma_amount', 0.5)}")
    last_stream = "[cpu_processed]"
    filter_complex_chains.extend([
        f"{video_stream_spec}scale_cuda={target_res_colon}:force_original_aspect_ratio=increase[gpu_scaled]",
        ",".join(cpu_filters) + last_stream,
    ])
    if use_timer:
        pos = ring_cfg.get('position', {})
        ring_size = ring_cfg.get('size', 600)
        timer_pix_fmt = 'yuva444p10le'
        filter_complex_chains.extend([
            f"[{timer_input_index}:v]scale={ring_size}:-1,format={timer_pix_fmt}[timer]",
            f"{last_stream}[timer]overlay=x='{pos.get('x', '(W-w)/2')}':y='{pos.get('y', '50')}'[with_timer]",
        ])
        last_stream = "[with_timer]"
    clean_text = prepare_text_for_ffmpeg(name, title_cfg.get('wrap_at_char', 25))
    font_path = title_cfg.get('font_file', '').replace('\\', '/').replace(':', '\\:')
    video_chain_suffix = (
        f"drawtext=fontfile='{font_path}':text='{clean_text}':"
        f"fontsize={title_cfg.get('font_size', 80)}:fontcolor={title_cfg.get('font_color', 'white')}:"
        f"box=1:boxcolor={title_cfg.get('box_color', 'black@0.7')}:"
        f"boxborderw={title_cfg.get('box_border_width', 15)}:"
        f"x='{title_cfg.get('position_x', '(w-text_w)/2')}':y='{title_cfg.get('position_y', 'h*0.8')}',"
        f"setsar=1[final_v]"
    )
    filter_complex_chains.append(f"{last_stream}{video_chain_suffix}")

    audio_streams_to_mix: list[str] = []
    audio_filter_chains: list[str] = []
    audio_opt_cfg = cfg.get('audio_optimization', {})
    vocal_enhance_cfg = audio_opt_cfg.get('vocal_enhancement', {})
    main_audio_chain_parts = [
        f"{audio_stream_spec}aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS"
    ]
    if audio_opt_cfg.get('enabled') and vocal_enhance_cfg.get('enabled'):
        log("    - Applying vocal enhancement (EQ/Compression)...")
        hp_hz = vocal_enhance_cfg.get('highpass_hz', 80)
        pb_hz = vocal_enhance_cfg.get('presence_boost_hz', 2500)
        pb_db = vocal_enhance_cfg.get('presence_boost_db', 2)
        comp_params = vocal_enhance_cfg.get('compression_params', '')
        main_audio_chain_parts.append(f"highpass=f={hp_hz}")
        main_audio_chain_parts.append(f"equalizer=f={pb_hz}:width_type=q:width=2:g={pb_db}")
        if comp_params:
            main_audio_chain_parts.append(comp_params)
    audio_filter_chains.append(",".join(main_audio_chain_parts) + "[main_a]")
    audio_streams_to_mix.append("[main_a]")

    bgm_stream_for_mixing, sfx_stream_for_mixing = "", ""
    if use_bgm:
        bgm_vol = float(bgm_cfg.get('master_volume', 1.0))
        audio_filter_chains.append(
            f"[{bgm_input_index}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={bgm_vol:.2f}[bgm_vol]"
        )
        bgm_stream_for_mixing = "[bgm_vol]"

    if sfx_rule_to_apply:
        sfx_details = sfx_cfg['effects'][sfx_rule_to_apply['effect']]
        sfx_vol = sfx_details.get('volume', 1.0) * sfx_cfg.get('master_volume', 1.0)
        delay_ms = sfx_delay_ms
        audio_filter_chains.append(
            f"[{sfx_input_index}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={sfx_vol:.2f},adelay={delay_ms}|{delay_ms}[delayed_sfx]"
        )
        sfx_stream_for_mixing = "[delayed_sfx]"

    ducking_enabled = bgm_cfg.get('ducking_enabled', False)
    if use_bgm and sfx_stream_for_mixing and ducking_enabled:
        duck_vol_ratio = bgm_cfg.get('ducking_volume', 0.2)
        audio_filter_chains.append(f"{sfx_stream_for_mixing}asplit[sfx_mix][sfx_sc]")
        sfx_stream_for_mixing = "[sfx_mix]"
        audio_filter_chains.append(
            f"{bgm_stream_for_mixing}[sfx_sc]sidechaincompress=threshold=0.01:ratio=5:level_sc={duck_vol_ratio}[bgm_ducked]"
        )
        bgm_stream_for_mixing = "[bgm_ducked]"

    if bgm_stream_for_mixing:
        audio_streams_to_mix.append(bgm_stream_for_mixing)
    if sfx_stream_for_mixing:
        audio_streams_to_mix.append(sfx_stream_for_mixing)

    final_audio_stream = "[main_a]"
    if len(audio_streams_to_mix) > 1:
        mix_inputs_str = "".join(audio_streams_to_mix)
        audio_filter_chains.append(
            f"{mix_inputs_str}amix=inputs={len(audio_streams_to_mix)}:duration=first:dropout_transition=1[mixed_a]"
        )
        final_audio_stream = "[mixed_a]"

    audio_map_target = final_audio_stream
    if video_cfg.get('audio_channels', 2) == 1:
        audio_filter_chains.append(f"{final_audio_stream}pan=mono|c0=c0[final_a]")
        audio_map_target = "[final_a]"

    filter_complex_chains.extend(audio_filter_chains)
    filter_complex = ";".join(filter_complex_chains)

    final_cmd_args = ['-filter_complex', filter_complex, '-map', '[final_v]', '-map', audio_map_target]
    final_cmd_args.extend([
        '-c:v', video_cfg['codec'], '-preset', video_cfg['preset'], '-cq', str(video_cfg['quality']),
        '-pix_fmt', pix_fmt, '-c:a', video_cfg['audio_codec'], '-b:a', video_cfg['audio_bitrate'],
        '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    ])
    if video_cfg.get('codec') in ('h264_nvenc', 'hevc_nvenc'):
        # 'qres' (quarter-res first pass) is ~1.5x faster than 'fullres' with
        # quality differences typically <0.05 dB PSNR -- visually indistinguishable.
        final_cmd_args += [
            '-rc-lookahead', '20', '-spatial_aq', '1', '-temporal_aq', '1', '-aq-strength', '8',
            '-rc', 'vbr', '-tune', 'hq', '-multipass', 'qres', '-bf', '3',
        ]
        if video_cfg.get('codec') == 'hevc_nvenc':
            final_cmd_args += ['-profile:v', 'main10' if bit_depth == 10 else 'main']
    ffmpeg_cmd.extend(final_cmd_args)
    ffmpeg_cmd.extend(['-t', str(length), output_segment_file])

    if verbose_mode:
        log("    - Assembled FFmpeg command: " + ' '.join(f'"{c}"' for c in ffmpeg_cmd))

    log("  > Step 3/3: Encoding with FFmpeg...")
    encoding_start_time = time.monotonic()
    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        err_tail = (e.stderr or '').strip().splitlines()[-30:] if e.stderr else []
        raise RuntimeError(
            f"FFmpeg failed on segment '{name}':\n" + "\n".join(err_tail)
        ) from e
    log(f"    - Done. Segment encoded in {time.monotonic() - encoding_start_time:.2f}s.")

    if task.get('fingerprint'):
        _update_manifest_entry(output_segment_file, task['fingerprint'])

    return logs


# --- Main Logic ---
def assemble_video(
    config_path: str,
    routine_path: str,
    source_video_path: str,
    output_path: str,
    background_music_path: str | None,
    segments_to_process: list[int] | None = None,
    source_start_offset: float = 0.0,
    source_end_limit: float | None = None,
    test_mode: bool = False,
    verbose_mode: bool = False,
    force_render: bool = False
):
    total_start_time = time.monotonic()

    try:
        with open(config_path, 'r', encoding='utf-8') as f: cfg = yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(f"FATAL: Config file not found at '{config_path}'")
    try:
        with open(routine_path, 'r', encoding='utf-8') as f: routine = yaml.safe_load(f)
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
    bgm_cfg = cfg.get('background_music', {})

    if test_mode:
        print("\n--- 🧪 TEST MODE ENABLED 🧪 ---")
        if cfg.get('test_mode_settings'):
            video_cfg.update(cfg.get('test_mode_settings'))
    if force_render:
        print("\n--- 💥 FORCED RE-RENDER ENABLED 💥 ---")

    # === Pre-bake LUT chain ONCE (cached) for the whole run ===
    apply_lut = source_cfg.get('apply_lut', False)
    lut_files_cfg = source_cfg.get('lut_files', []) or []
    effective_luts: list[str] = []
    if apply_lut and isinstance(lut_files_cfg, list) and lut_files_cfg:
        existing_luts = [lf for lf in lut_files_cfg if os.path.exists(lf)]
        for missing in [lf for lf in lut_files_cfg if not os.path.exists(lf)]:
            print(f"  > WARNING: LUT file not found, skipping: {missing}")
        if len(existing_luts) > 1:
            try:
                from combine_luts import get_or_build_combined_lut
                baked = get_or_build_combined_lut(existing_luts)
                print(f"  > LUT pre-bake: {len(existing_luts)} LUTs combined into {os.path.basename(baked)}")
                effective_luts = [baked]
            except Exception as e:
                print(f"  > WARNING: LUT pre-bake failed ({e}); falling back to chained lut3d.")
                effective_luts = existing_luts
        else:
            effective_luts = existing_luts

    # Switch to HEVC once (was previously detected per-segment).
    if int(video_cfg.get('bit_depth', 8)) == 10 and 'h264' in video_cfg.get('codec', ''):
        print("  > INFO: Switching to HEVC codec for 10-bit output.")
        video_cfg['codec'] = 'hevc_nvenc'

    ctx = {
        'cfg': cfg, 'paths_cfg': paths_cfg, 'video_cfg': video_cfg,
        'title_cfg': title_cfg, 'ring_cfg': ring_cfg, 'source_cfg': source_cfg,
        'finish_cfg': finish_cfg, 'sfx_cfg': sfx_cfg, 'bgm_cfg': bgm_cfg,
        'effective_luts': effective_luts,
    }

    print("--- 🏋️ Starting Video Assembly 🏋️ ---")
    if source_start_offset > 0:
        print(f"  > Using source video starting from {source_start_offset:.2f}s.")
    if source_end_limit is not None:
        print(f"  > Capping source video at {source_end_limit:.2f}s.")

    # === PASS 1: Build task list (sequential, cheap) ===
    manifest = _load_manifest()
    try:
        source_video_mtime = os.path.getmtime(source_video_path)
    except OSError:
        source_video_mtime = 0
    bgm_mtime = (os.path.getmtime(background_music_path)
                 if background_music_path and os.path.exists(background_music_path) else 0)

    tasks: list[dict] = []
    routine_elapsed_time = 0.0

    for i, exercise in enumerate(routine):
        segment_number = i + 1
        name = exercise.get('name', '...').title()
        length = float(exercise.get('length', 0))
        if length < 0:
            print(f"\n  > WARNING: Segment {segment_number} '{name}' has negative length ({length}); treating as 0.")
            length = 0.0
        elif length > 0 and abs(length - round(length)) > 1e-6:
            print(f"  > NOTE: Segment {segment_number} '{name}' has fractional length ({length}s). "
                  f"Timer asset will be rounded to {int(length)}s.")
        start_time_in_source = source_start_offset + routine_elapsed_time
        end_time_in_source = start_time_in_source + length

        if segments_to_process and segment_number not in segments_to_process:
            if verbose_mode:
                print(f"\nSkipping Segment {segment_number}/{len(routine)}: '{name}'")
            # Still keep the existing temp in the concat list so the final
            # video isn't truncated when the user only re-renders a subset.
            if os.path.exists(output_segment_file) and os.path.getsize(output_segment_file) > 0:
                tasks.append({'reuse': True, 'output': output_segment_file, 'i': i, 'name': name})
            routine_elapsed_time += length
            continue
        if length <= 0:
            if verbose_mode:
                print(f"\nSkipping Segment {segment_number}/{len(routine)}: '{name}' (zero length).")
            routine_elapsed_time += length
            continue
        if source_end_limit is not None and end_time_in_source > source_end_limit:
            print(f"\n  > WARNING: Segment '{name}' would end past specified end point. Stopping.")
            break

        output_segment_file = f"temp_segment_{i}.mp4"

        replacement_video_path = exercise.get('replace_video')
        replacement_audio_path = exercise.get('replace_audio')
        has_video_replacement = bool(replacement_video_path and os.path.exists(replacement_video_path))
        has_audio_replacement = bool(replacement_audio_path and os.path.exists(replacement_audio_path))

        final_video_input_path = replacement_video_path if has_video_replacement else source_video_path
        final_video_input_args = [] if has_video_replacement else [
            '-ss', str(start_time_in_source), '-to', str(end_time_in_source)]
        final_audio_input_path = replacement_audio_path if has_audio_replacement else source_video_path
        final_audio_input_args = [] if has_audio_replacement else [
            '-ss', str(start_time_in_source), '-to', str(end_time_in_source)]

        timer_duration = int(length)
        timer_file = os.path.join(
            paths_cfg.get('asset_output_dir', '.'),
            paths_cfg.get('timers_subdir', 'timers'),
            f'timer_{timer_duration}s.mov',
        )
        use_timer = os.path.exists(timer_file)

        use_bgm = bool(background_music_path
                       and os.path.exists(background_music_path)
                       and bgm_cfg.get('enabled', False))
        if not use_bgm and background_music_path and not bgm_cfg.get('enabled', False):
            # Print this once, on the first segment that would have used BGM.
            if i == 0:
                print("  > NOTE: BGM specified but 'enabled' is false in config or file missing. Skipping BGM.")
        bgm_offset = routine_elapsed_time

        # Resolve SFX rule deterministically (per-segment seeded RNG so reruns
        # produce identical output regardless of parallel scheduling order).
        rng = random.Random(f"{source_video_path}|{i}|{name}")
        sfx_rule_to_apply = None
        if sfx_cfg.get('rules') and sfx_cfg.get('effects'):
            for rule in sfx_cfg['rules']:
                if any(trigger == '*' or trigger.lower() in name.lower()
                       for trigger in rule.get('triggers', [])):
                    if rng.random() < rule.get('play_percent', 100) / 100.0:
                        sfx_rule_to_apply = rule
                        break
        sfx_delay_ms = 0
        if sfx_rule_to_apply:
            effect_details = sfx_cfg['effects'].get(sfx_rule_to_apply.get('effect'), {})
            sfx_path = effect_details.get('file')
            if not (sfx_path and os.path.exists(sfx_path)):
                print(f"    - WARNING: Sound effect file not found for segment '{name}'. Skipping.")
                sfx_rule_to_apply = None
            else:
                start_time_param = sfx_rule_to_apply.get('start_time', 0.0)
                if isinstance(start_time_param, (int, float)):
                    sfx_delay_ms = int(
                        (length - abs(start_time_param) if start_time_param < 0 else start_time_param) * 1000)
                elif start_time_param == 'random':
                    sfx_delay_ms = rng.randint(0, int(length * 1000))

        # Manifest fingerprint covers every input that affects the rendered bytes.
        fingerprint_payload = {
            'i': i, 'name': name, 'length': length,
            'start': start_time_in_source, 'end': end_time_in_source,
            'src': os.path.abspath(source_video_path), 'src_mtime': source_video_mtime,
            'replace_v': replacement_video_path,
            'replace_v_mtime': os.path.getmtime(replacement_video_path) if has_video_replacement else 0,
            'replace_a': replacement_audio_path,
            'replace_a_mtime': os.path.getmtime(replacement_audio_path) if has_audio_replacement else 0,
            'timer_file': timer_file if use_timer else None,
            'use_bgm': use_bgm, 'bgm_offset': bgm_offset,
            'bgm_path': os.path.abspath(background_music_path) if use_bgm else None,
            'bgm_mtime': bgm_mtime,
            'sfx_rule': sfx_rule_to_apply, 'sfx_delay_ms': sfx_delay_ms,
            'video_cfg': video_cfg, 'source_cfg': source_cfg, 'finish_cfg': finish_cfg,
            'title_cfg': title_cfg, 'ring_cfg': ring_cfg, 'bgm_cfg': bgm_cfg, 'sfx_cfg': sfx_cfg,
            'audio_opt': cfg.get('audio_optimization', {}),
            'effective_luts': effective_luts,
        }
        fingerprint = _segment_fingerprint(fingerprint_payload)

        # Reuse via manifest (no ffprobe call) when fingerprint matches.
        if (not force_render
                and os.path.exists(output_segment_file)
                and os.path.getsize(output_segment_file) > 0
                and manifest.get(output_segment_file) == fingerprint):
            print(f"\nReusing Segment {segment_number}/{len(routine)}: '{name}' (manifest hit)")
            tasks.append({'reuse': True, 'output': output_segment_file, 'i': i, 'name': name})
            routine_elapsed_time += length
            continue
        # Pre-manifest renders are NOT reused: we can't verify their inputs
        # match the current fingerprint, so persisting a stamp here could
        # silently lock in a stale render forever. Force a re-encode instead.

        tasks.append({
            'reuse': False, 'i': i, 'segment_number': segment_number,
            'total_segments': len(routine),
            'name': name, 'length': length,
            'start_time_in_source': start_time_in_source,
            'end_time_in_source': end_time_in_source,
            'output': output_segment_file,
            'video_input_path': final_video_input_path,
            'video_input_args': final_video_input_args,
            'audio_input_path': final_audio_input_path,
            'audio_input_args': final_audio_input_args,
            'replaced_video': has_video_replacement,
            'replaced_audio': has_audio_replacement,
            'timer_file': timer_file, 'use_timer': use_timer,
            'use_bgm': use_bgm, 'bgm_offset': bgm_offset,
            'background_music_path': background_music_path,
            'sfx_rule_to_apply': sfx_rule_to_apply,
            'sfx_delay_ms': sfx_delay_ms,
            'fingerprint': fingerprint,
        })
        routine_elapsed_time += length

    # === PASS 2: Render in parallel ===
    work = [t for t in tasks if not t.get('reuse')]
    perf_cfg = cfg.get('performance', {})
    num_workers = max(1, int(perf_cfg.get('num_workers', 1)))
    if work:
        effective_workers = min(num_workers, len(work))
        print(f"\n--- 🧵 Rendering {len(work)} segment(s) with {effective_workers} worker(s) in parallel ---")
        if effective_workers <= 1:
            for t in work:
                lines = _render_segment(t, ctx, verbose_mode)
                for line in lines:
                    print(line)
        else:
            failures: list[tuple[dict, Exception]] = []
            with ThreadPoolExecutor(max_workers=effective_workers) as ex:
                future_to_task = {ex.submit(_render_segment, t, ctx, verbose_mode): t for t in work}
                for fut in as_completed(future_to_task):
                    t = future_to_task[fut]
                    try:
                        lines = fut.result()
                        for line in lines:
                            print(line)
                    except Exception as e:
                        failures.append((t, e))
            if failures:
                for t, e in failures:
                    print(f"\n--- FATAL: Segment '{t['name']}' failed: {e} ---")
                sys.exit(1)

    segment_files = [t['output'] for t in tasks]

    # Drop manifest entries we no longer reference (e.g., from prior runs that
    # used a different routine length) so the cache doesn't grow forever.
    _prune_manifest(set(segment_files))

    if not segment_files: sys.exit("\nNo segments were created.")
    if len(segment_files) == 1:
        print("\n--- 🎞️ Finalizing Single Segment ---"); shutil.move(segment_files[0], output_path); print(f"  > Renamed '{segment_files[0]}' to '{output_path}'.")
    else:
        print(f"\n--- 🎞️ Concatenating {len(segment_files)} Segments ---")
        concat_file = "concat_list.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            for file in segment_files: f.write(f"file '{Path(file).resolve().as_posix()}'\n")
        # Stream-copy both video and audio: every segment was encoded with identical
        # codec/params so concat is lossless, and we avoid an AAC re-encode here
        # (loudness normalization will do the only audio re-encode after this).
        concat_cmd = [ 'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', output_path ]
        if verbose_mode: print("    - Running concat command:", " ".join(concat_cmd))
        try:
            subprocess.run(concat_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
            print("  > Concatenation finished successfully.")
        except subprocess.CalledProcessError as e:
            if not verbose_mode:
                print("  > FFmpeg error output (stderr):", e.stderr)
            sys.exit(1)
        finally:
            if os.path.exists(concat_file): os.remove(concat_file)

    print("\n--- 🧹 Cleaning Up Temporary Files ---")
    # Only delete temps that were freshly rendered this run. Reused temps must
    # stay on disk so the next run can hit the manifest cache without
    # re-encoding everything.
    freshly_rendered = {t['output'] for t in tasks if not t.get('reuse')}
    for file in segment_files:
        if file in freshly_rendered and os.path.exists(file):
            os.remove(file)
    print(f"\n✅ Video assembly complete! Final video saved to: {output_path}")
    print(f"   Total time taken: {time.monotonic() - total_start_time:.2f} seconds.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser( description="Creates a complete exercise video from a source file and a routine plan.", formatter_class=argparse.ArgumentDefaultsHelpFormatter )
    parser.add_argument("routine_path", help="Path to routine YAML file.")
    parser.add_argument("source_video", help="Path to source video file.")
    parser.add_argument("output_video", help="Path for final output video.")
    parser.add_argument("--bgm", type=str, help="Path to the pre-generated background music file.")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in source video (seconds).")
    parser.add_argument("--end", type=float, help="End time in source video (seconds).")
    parser.add_argument("--segments", type=str, help="Comma-separated list of segments to process (e.g., '1,3,5').")
    parser.add_argument("--test", action="store_true", help="Enable test mode for a fast, low-quality preview render.")
    parser.add_argument("--force-render", action="store_true", help="Force re-rendering of all segments, ignoring existing temp files.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show the full FFmpeg command and its real-time output.")
    parser.add_argument("--config", type=str, default='config.yaml', help="Path to config file.")
    args = parser.parse_args()

    segments_to_run = [int(s.strip()) for s in args.segments.split(',')] if args.segments else None

    assemble_video(
        config_path=args.config,
        routine_path=args.routine_path,
        source_video_path=args.source_video,
        output_path=args.output_video,
        background_music_path=args.bgm,
        segments_to_process=segments_to_run,
        source_start_offset=args.start,
        source_end_limit=args.end,
        test_mode=args.test,
        verbose_mode=args.verbose,
        force_render=args.force_render
    )

    optimize_final_audio(
        config_path=args.config,
        video_file_path=args.output_video,
        verbose=args.verbose
    )