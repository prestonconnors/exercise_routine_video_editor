#!/usr/bin/env python

import yaml
from math import floor
import os
import argparse
import numpy as np

# Pillow is used for the fast progress bar and reliable text drawing
from PIL import Image, ImageDraw, ImageFont

from moviepy import (
    VideoFileClip,
    TextClip,
    CompositeVideoClip,
    ColorClip,
    ImageClip,
    VideoClip,
    concatenate_videoclips
)

def calculate_safe_position(video_size, asset_size, position_strings, margins_percent):
    # ... (This helper function remains unchanged) ...
    video_w, video_h = video_size
    asset_w, asset_h = asset_size
    margin_x = video_w * (margins_percent['horizontal_percent'] / 100)
    margin_y = video_h * (margins_percent['vertical_percent'] / 100)
    if position_strings[0] == 'left': x = margin_x
    elif position_strings[0] == 'center': x = (video_w - asset_w) / 2
    elif position_strings[0] == 'right': x = video_w - asset_w - margin_x
    if position_strings[1] == 'top': y = margin_y
    elif position_strings[1] == 'center': y = (video_h - asset_h) / 2
    elif position_strings[1] == 'bottom': y = video_h - asset_h - margin_y
    return (x, y)

def create_workout_video(yaml_file, input_video_file, output_video_file, config_file, is_test_mode=False, use_gpu=False):
    """ Main function to process and generate the workout video. """
    
    print(f"Loading visual configuration from: {config_file}")
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading or parsing config file: {e}")
        return

    print(f"Loading workout plan from: {yaml_file}")
    try:
        with open(yaml_file, 'r') as file:
            workout_plan = yaml.safe_load(file)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading or parsing YAML file: {e}")
        return

    print(f"Loading input video from: {input_video_file}")
    if not os.path.exists(input_video_file):
        print(f"Error: Input video not found at '{input_video_file}'")
        return
    base_video = VideoFileClip(input_video_file)

    total_workout_duration = sum(ex.get('length', 0) for ex in workout_plan if ex.get('type') not in ['warmup', 'cool down', 'rest'])
    print(f"Total workout duration (excluding non-workout parts): {total_workout_duration} seconds.")
    
    processed_clips = []
    current_time = 0.0

    # --- Countdown Timer Setup ---
    cfg_timer = config['countdown_timer']
    # Use the specific timer font, or fall back to the global font
    countdown_font_file = cfg_timer.get('font_file', config['font_file'])
    
    dummy_countdown_clip = TextClip(
        text="00", font=countdown_font_file, font_size=cfg_timer['font_size'], 
        color=config['font_color'], stroke_color=config['stroke_color'], 
        stroke_width=cfg_timer['stroke_width']
    )
    countdown_size = dummy_countdown_clip.size
    
    try:
        pillow_font = ImageFont.truetype(countdown_font_file, cfg_timer['font_size'])
    except IOError:
        print(f"Font not found at {countdown_font_file}, using default.")
        pillow_font = ImageFont.load_default()

    for i, exercise in enumerate(workout_plan):
        print(f"Processing clip {i+1}/{len(workout_plan)}: {exercise['name']} ({exercise.get('length', 0)}s)")
        start_time, end_time = current_time, current_time + exercise.get('length', 0)
        
        if end_time > base_video.duration: end_time = base_video.duration
        if start_time >= end_time: continue
            
        video_subclip = base_video.subclipped(start_time, end_time)
        clips_to_composite = [video_subclip]

        # --- Create and Position Exercise Name ---
        cfg_ex_name = config['exercise_name']
        # Use the specific font, or fall back to the global font
        ex_name_font = cfg_ex_name.get('font_file', config['font_file'])
        exercise_name_text = TextClip(
            text=exercise['name'].upper(), font=ex_name_font, font_size=cfg_ex_name['font_size'], 
            color=config['font_color'], stroke_color=config['stroke_color'], 
            stroke_width=cfg_ex_name['stroke_width'], margin=(cfg_ex_name['margin'], cfg_ex_name['margin'])
        )
        ex_name_pos = calculate_safe_position(base_video.size, exercise_name_text.size, cfg_ex_name['position'], config['safe_margins'])
        clips_to_composite.append(exercise_name_text.with_position(ex_name_pos).with_duration(video_subclip.duration))

        # --- Create and Position Countdown Timer ---
        def make_countdown_frame(t, subclip_duration=video_subclip.duration):
            time_left = max(0, floor(subclip_duration - t))
            text_to_draw = str(time_left)
            canvas = Image.new('RGB', countdown_size, cfg_timer['background_color'])
            draw = ImageDraw.Draw(canvas)
            center_x = countdown_size[0] / 2
            center_y = countdown_size[1] / 2
            draw.text(
                (center_x, center_y), text_to_draw, font=pillow_font, anchor="mm",
                fill=config['font_color'], stroke_width=cfg_timer['stroke_width'],
                stroke_fill=config['stroke_color']
            )
            return np.array(canvas)

        countdown_pos = calculate_safe_position(base_video.size, countdown_size, cfg_timer['position'], config['safe_margins'])
        countdown_clip = VideoClip(make_countdown_frame, duration=video_subclip.duration).with_position(countdown_pos)
        clips_to_composite.append(countdown_clip)
        
        # --- Create and Position Progress Bar ---
        if exercise.get('type') not in ['warmup', 'cool down', 'rest']:
            def make_progress_bar_frame(t, captured_start_time=start_time):
                warmup_duration = workout_plan[0].get('length', 0) if workout_plan and workout_plan[0].get('type') == 'warmup' else 0
                time_elapsed = captured_start_time + t - warmup_duration
                progress = max(0, time_elapsed / total_workout_duration) if total_workout_duration > 0 else 0
                
                cfg_bar = config['progress_bar']
                w, h = int(base_video.w), cfg_bar['height']
                bar_w = int(w * progress)

                bar_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(bar_img)
                draw.rectangle([(0, 0), (w, h)], fill=tuple(cfg_bar['background_color']))
                draw.rectangle([(0, 0), (bar_w, h)], fill=tuple(cfg_bar['foreground_color']))
                
                return np.array(bar_img)

            cfg_bar = config['progress_bar']
            bar_size = (base_video.w, cfg_bar['height'])
            bar_pos = calculate_safe_position(base_video.size, bar_size, cfg_bar['position'], config['safe_margins'])
            
            progress_bar_clip = VideoClip(make_progress_bar_frame, duration=video_subclip.duration).with_position(bar_pos)
            clips_to_composite.append(progress_bar_clip)
            
        # --- Create and Position "Next Up" Preview ---
        if i + 1 < len(workout_plan):
            next_exercise = workout_plan[i+1]
            if next_exercise['name'].lower() not in ['rest', 'cool down']:
                next_start_time = end_time
                if next_start_time < base_video.duration:
                    cfg_pip = config['next_up_preview']
                    cfg_pip_text = cfg_pip['text']
                    # Use the specific font, or fall back to the global font
                    pip_font = cfg_pip_text.get('font_file', config['font_file'])
                    
                    preview_clip = base_video.subclipped(next_start_time, min(next_start_time + 5, base_video.duration)).with_fps(15)
                    pip_width = base_video.w * cfg_pip['scale']
                    preview_clip_resized = preview_clip.resized(width=pip_width)
                    next_up_text = TextClip(
                        text="NEXT UP:", font=pip_font, font_size=cfg_pip_text['font_size'],
                        color=config['font_color'], stroke_color=config['stroke_color'],
                        stroke_width=cfg_pip_text['stroke_width']
                    )
                    text_bg = ColorClip(size=(int(next_up_text.w * 1.1), int(next_up_text.h * 1.2)), color=(0,0,0)).with_opacity(0.6)
                    text_with_bg = CompositeVideoClip([text_bg, next_up_text.with_position('center')])
                    next_up_group = CompositeVideoClip([preview_clip_resized, text_with_bg.with_position(('center', 0.05), relative=True)], size=preview_clip_resized.size)
                    
                    pip_pos = calculate_safe_position(base_video.size, next_up_group.size, cfg_pip['position'], config['safe_margins'])

                    base_pip = (next_up_group
                                 .with_start(max(0, video_subclip.duration - cfg_pip['show_before_end_seconds']))
                                 .with_duration(cfg_pip['show_before_end_seconds'])
                                 .with_position(pip_pos))
                    
                    fade_mask = create_fade_mask(base_pip.duration, 0.5, base_pip.size)
                    next_up_pip = base_pip.with_mask(fade_mask)
                    clips_to_composite.append(next_up_pip)
        
        final_subclip = CompositeVideoClip(clips_to_composite, size=base_video.size)
        processed_clips.append(final_subclip)
        current_time = end_time

        if current_time >= base_video.duration:
            print("Reached end of base video. Stopping processing.")
            break

    if not processed_clips:
        print("No clips were created. Exiting.")
        return
        
    print("Concatenating all clips...")
    final_video = concatenate_videoclips(processed_clips)

    thread_count = os.cpu_count()
    print(f"\nUsing {thread_count} CPU threads for encoding.")

    render_fps = base_video.fps
    render_settings = {
        "codec": "libx264", "audio_codec": "aac", "threads": thread_count,
        "preset": 'medium', "logger": 'bar', "audio": True, "fps": render_fps
    }

    if is_test_mode:
        print("--- TEST MODE ENABLED ---")
        print("Rendering a fast, low-quality, silent video at 480p resolution and 15fps.")
        final_video = final_video.resized(width=480)
        render_settings.update({"audio": False, "fps": 15, "preset": 'ultrafast'})

    if use_gpu:
        print("--- GPU MODE ENABLED ---")
        render_settings["codec"] = 'h264_nvenc'
        render_settings["preset"] = 'p4' if not is_test_mode else 'p1'
        print(f"Attempting to use GPU codec: {render_settings['codec']} with preset: {render_settings['preset']}")
    else:
        print(f"Rendering with CPU codec: {render_settings['codec']} with preset: {render_settings['preset']}")

    try:
        final_video.write_videofile(output_video_file, **render_settings)
        print(f"\nSuccessfully created {output_video_file}!")
    except Exception as e:
        print(f"\n--- RENDERING FAILED ---")
        print(f"Error: {e}")
        if use_gpu:
            print("GPU rendering can fail due to missing drivers or unsupported FFmpeg builds.")
    
    finally:
        if 'base_video' in locals(): base_video.close()
        if 'final_video' in locals(): final_video.close()

def create_fade_mask(clip_duration, fade_duration, clip_size):
    """ Creates a grayscale VideoClip mask for fade effects. """
    def make_mask_frame(t):
        opacity = 1.0
        if t < fade_duration:
            opacity = t / fade_duration
        elif (clip_duration - t) < fade_duration:
            opacity = (clip_duration - t) / fade_duration
        frame = np.full((clip_size[1], clip_size[0]), opacity, dtype=np.float32)
        return frame
    return VideoClip(make_mask_frame, is_mask=True, duration=clip_duration)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automates the creation of workout videos with timed overlays.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-y', '--yaml', required=True, help="Path to the workout routine YAML file.")
    parser.add_argument('-i', '--input', required=True, help="Path to the input raw video file.")
    parser.add_argument('-o', '--output', required=True, help="Path for the final output video file.")
    parser.add_argument('-c', '--config', default='config.yaml', help="Path to the visual configuration YAML file (default: config.yaml).")
    parser.add_argument('-t', '--test', action='store_true', help="Enable test mode for fast, low-quality rendering.")
    parser.add_argument('--gpu', action='store_true', help="Attempt to use GPU hardware acceleration for encoding.")
    
    args = parser.parse_args()
    create_workout_video(args.yaml, args.input, args.output, args.config, args.test, args.gpu)