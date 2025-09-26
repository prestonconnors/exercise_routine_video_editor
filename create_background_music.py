import os
import sys
import yaml
import random
import subprocess
import argparse
from pathlib import Path
import math
from collections import deque

# A small cache to avoid repeated ffprobe calls for the same file
DURATION_CACHE = {}

def get_audio_duration(file_path):
    """Returns the duration of an audio file in seconds, with caching."""
    if not file_path: return 0
    abs_path = os.path.abspath(file_path)
    if abs_path in DURATION_CACHE:
        return DURATION_CACHE[abs_path]

    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)]
    try:
        duration_str = subprocess.check_output(cmd, text=True, encoding='utf-8').strip()
        duration = float(duration_str)
        DURATION_CACHE[abs_path] = duration
        return duration
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"Warning: Could not get duration for '{file_path}': {e}")
        return 0

def scan_and_shuffle(folder_path):
    """Scans a folder recursively for music and returns a shuffled deque and the source list."""
    if not folder_path or not folder_path.is_dir():
        return deque(), []
    files = [p for p in folder_path.rglob('*') if p.is_file() and p.suffix.lower() in ['.mp3', '.wav', '.flac', '.m4a']]
    random.shuffle(files)
    return deque(files), files

def create_background_music(
    routine_path: str,
    output_path_str: str,
    config_path: str = 'config.yaml',
    verbose_mode: bool = False
):
    output_path = Path(output_path_str)
    try:
        with open(config_path, 'r', encoding='utf-8') as f: cfg = yaml.safe_load(f)
    except FileNotFoundError: sys.exit(f"FATAL: Config file not found at '{config_path}'")
    try:
        with open(routine_path, 'r', encoding='utf-8') as f: routine = yaml.safe_load(f)
    except FileNotFoundError: sys.exit(f"FATAL: Routine file not found at '{routine_path}'")

    bgm_cfg = cfg.get('background_music', {})
    if not bgm_cfg.get('enabled', False):
        print("Background music is disabled. Exiting.")
        return

    total_duration = sum(float(ex.get('length', 0)) for ex in routine)
    if total_duration <= 0: sys.exit("Routine has zero duration.")
    
    crossfade_duration = float(bgm_cfg.get('crossfade_duration', 0.0))

    print(f"--- Creating Continuous Background Music ---")
    print(f"  > Total duration: {total_duration:.2f}s.")
    if crossfade_duration > 0: print(f"  > Crossfades enabled ({crossfade_duration}s).")

    # --- 1. Prepare Music Libraries ---
    main_music_folder = Path(bgm_cfg.get('music_folder', 'assets/music'))
    global_playlist_deque, global_source_files = scan_and_shuffle(main_music_folder)
    
    rules = bgm_cfg.get('rules', [])
    rule_playlists = {}
    
    print("  > Scanning music sources...")
    print(f"    - Main library: Found {len(global_source_files)} tracks in '{main_music_folder}'.")
    for rule in rules:
        if 'folder' in rule:
            folder_path = Path(rule['folder'])
            if folder_path.is_dir():
                d, s = scan_and_shuffle(folder_path)
                rule_playlists[rule['folder']] = {'deque': d, 'source_files': s}
                print(f"    - Rule '{rule.get('name')}': Found {len(s)} tracks in '{folder_path}'.")

    # --- 2. Build High-Level "Song Block" Timeline ---
    song_blocks = []
    
    active_track = None
    active_track_played = 0.0
    
    active_playlist_deque = global_playlist_deque
    active_source_files = global_source_files

    current_block = None

    print("\n  > Planning audio timeline...")
    for i, exercise in enumerate(routine):
        seg_dur = float(exercise.get('length', 0)); time_left_in_seg = seg_dur
        if seg_dur <= 0: continue
        ex_name = exercise.get('name', '')
        
        # Check for rules and determine if an interruption is needed
        matched_rule = next((r for r in rules if any(t.lower() in ex_name.lower() for t in r.get('triggers',[])) and (Path(r.get('file','')).exists() or r.get('folder') in rule_playlists)), None)
        
        interruption_forced = False
        
        if matched_rule:
            rule_name = matched_rule.get('name', 'Untitled Rule')
            
            if matched_rule.get('mode') == 'loop':
                if current_block: song_blocks.append(current_block)
                
                rule_file = Path(matched_rule['file'])
                print(f"    - Segment {i+1} ('{ex_name}'): Overriding with LOOPING file '{rule_file.name}'.")
                song_blocks.append({'file': rule_file, 'start': 0, 'duration': seg_dur, 'mode': 'loop'})
                
                current_block = None; active_track = None
                active_playlist_deque = global_playlist_deque
                active_source_files = global_source_files
                continue

            if 'folder' in matched_rule:
                folder_data = rule_playlists.get(matched_rule['folder'])
                if folder_data and active_playlist_deque is not folder_data['deque']:
                    print(f"    - Segment {i+1} ('{ex_name}'): '{rule_name}' triggered, switching to its playlist.")
                    active_playlist_deque = folder_data['deque']
                    active_source_files = folder_data['source_files']
                    interruption_forced = True
            
            elif 'file' in matched_rule:
                rule_file = Path(matched_rule['file'])
                if active_track != rule_file:
                    print(f"    - Segment {i+1} ('{ex_name}'): Rule forces new track '{rule_file.name}'.")
                    active_track = rule_file; active_track_played = 0.0
                    interruption_forced = True
                    active_playlist_deque = global_playlist_deque
                    active_source_files = global_source_files
        else:
            if active_playlist_deque is not global_playlist_deque:
                 print(f"    - Segment {i+1} ('{ex_name}'): No rule. Current song will continue; next track from Main playlist.")
                 active_playlist_deque = global_playlist_deque
                 active_source_files = global_source_files
                 
        if interruption_forced:
            if current_block: song_blocks.append(current_block)
            current_block = None
            if not (matched_rule and 'file' in matched_rule): active_track = None

        while time_left_in_seg > 0.001:
            if active_track is None or active_track_played >= get_audio_duration(active_track):
                if current_block: song_blocks.append(current_block)
                current_block = None

                if not active_playlist_deque:
                    if not active_source_files:
                        song_blocks.append({'file': None, 'duration': time_left_in_seg})
                        break
                    print(f"    - Playlist exhausted. Reshuffling {len(active_source_files)} tracks...")
                    random.shuffle(active_source_files)
                    active_playlist_deque.extend(active_source_files)
                
                active_track = active_playlist_deque.popleft(); active_track_played = 0.0
                print(f"    - Starting new track: '{active_track.name}'")

            if not current_block:
                current_block = {'file': active_track, 'start': active_track_played, 'duration': 0}

            track_rem = get_audio_duration(active_track) - (current_block['start'] + current_block['duration'])
            play_dur = min(time_left_in_seg, track_rem)
            
            current_block['duration'] += play_dur; active_track_played += play_dur
            time_left_in_seg -= play_dur

    if current_block: song_blocks.append(current_block)

    # --- 3. Build FFmpeg command from the song blocks ---
    ffmpeg_cmd = ['ffmpeg', '-y']
    filter_complex = []
    
    unique_files = sorted(list(set(b['file'] for b in song_blocks if b.get('file'))))
    file_to_idx = {file: i for i, file in enumerate(unique_files)}
    for file in unique_files: ffmpeg_cmd.extend(['-i', str(file)])
        
    print("\n  > Building FFmpeg filtergraph...")
    
    for i, block in enumerate(song_blocks):
        s_name = f"[b{i}]"
        if block.get('file') is None:
            filter_complex.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={block['duration']}{s_name}")
            continue
            
        idx=file_to_idx[block['file']]; dur=get_audio_duration(block['file'])
        if block.get('mode') == 'loop':
            loops = math.ceil(block['duration']/dur) - 1 if dur > 0 else 0
            chain = f"[{idx}:a]aloop=loop={loops if loops >= 0 else 0}:size={int(dur*48000)},atrim=duration={block['duration']:.3f},asetpts=PTS-STARTPTS{s_name}"
        else:
            chain = f"[{idx}:a]atrim=start={block['start']:.3f}:duration={block['duration']:.3f},asetpts=PTS-STARTPTS{s_name}"
        filter_complex.append(chain)

    last_chain = "[b0]"
    for i in range(1, len(song_blocks)):
        prev_b = song_blocks[i-1]; curr_b = song_blocks[i]
        out_name = f"[c{i}]"

        # ** THE CORRECTED LOGIC IS HERE **
        should_crossfade = (
            crossfade_duration > 0 and
            prev_b.get('file') is not None and
            curr_b.get('file') is not None and
            prev_b.get('file') != curr_b.get('file')
        )
        
        if should_crossfade:
            print(f"    - Applying crossfade: '{prev_b['file'].name}' -> '{curr_b['file'].name}'")
            filter_complex.append(f"{last_chain}[b{i}]acrossfade=duration={crossfade_duration}:curve1=tri:curve2=tri{out_name}")
        else:
            filter_complex.append(f"{last_chain}[b{i}]concat=n=2:v=0:a=1{out_name}")
        last_chain = out_name
        
    final_stream = last_chain
    fade_dur = bgm_cfg.get('fade_duration', 0)
    if fade_dur > 0 and total_duration > fade_dur * 2:
        fade_start = total_duration - fade_dur
        filter_complex.append(f"{last_chain}afade=type=in:duration={fade_dur},afade=type=out:start_time={fade_start:.3f}:duration={fade_dur}[final_a]")
        final_stream = "[final_a]"
        print(f"  > Applying {fade_dur}s global fade-in/out.")

    output_params = []; out_ext = output_path.suffix.lower()
    codec_map = {'.flac':'flac', '.mp3':'libmp3lame', '.m4a':'aac'}
    codec = codec_map.get(out_ext, 'aac')
    if codec == 'aac': output_params.extend(['-c:a', codec, '-b:a', '192k'])
    elif codec == 'libmp3lame': output_params.extend(['-c:a', codec, '-b:a', '320k'])
    else: output_params.extend(['-c:a', codec])
    print(f"  > Outputting with '{codec}' codec.")

    ffmpeg_cmd.extend(['-filter_complex', ";".join(filter_complex), '-map', final_stream])
    ffmpeg_cmd.append(str(output_path))
    
    if verbose_mode: print("\n  > Assembled FFmpeg command:", ' '.join(f"'{c}'" for c in ffmpeg_cmd))
        
    print("\n  > Encoding final audio file...")
    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=not verbose_mode, text=True, encoding='utf-8')
        print(f"\n✅ Background music created successfully: {output_path}")
    except subprocess.CalledProcessError as e:
        print("\n--- FATAL: FFmpeg failed. ---")
        if not verbose_mode: print("  > FFmpeg error (stderr):\n", e.stderr)
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generates continuous background music with crossfades.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("routine_path", help="Path to routine YAML file.")
    parser.add_argument("output_file", help="Path for the final audio file.")
    parser.add_argument("--config", default="config.yaml", help="Path to config file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show the full FFmpeg command.")
    
    args = parser.parse_args()
    create_background_music(
        routine_path=args.routine_path, output_path_str=args.output_file,
        config_path=args.config, verbose_mode=args.verbose
    )