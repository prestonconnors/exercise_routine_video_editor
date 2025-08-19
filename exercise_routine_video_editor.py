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

def create_workout_video(yaml_file, input_video_file, output_video_file, is_test_mode=False, use_gpu=False):
    """ Main function to process and generate the workout video. """
    FONT_FILE = 'C:/Windows/Fonts/arialbd.ttf' 
    FONT_COLOR = 'white'
    TEXT_STROKE_COLOR = 'black'
    TEXT_STROKE_WIDTH = 2
    
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

    # Create a dummy clip to establish the fixed size for our countdown box.
    dummy_countdown_clip = TextClip(
        text="00", font=FONT_FILE, font_size=120, color=FONT_COLOR,
        stroke_color=TEXT_STROKE_COLOR, stroke_width=TEXT_STROKE_WIDTH,
        margin=(15, 15)
    )
    countdown_size = dummy_countdown_clip.size
    
    try:
        pillow_font = ImageFont.truetype(FONT_FILE, 120)
    except IOError:
        print("Arial Bold font not found, using default.")
        pillow_font = ImageFont.load_default()

    for i, exercise in enumerate(workout_plan):
        print(f"Processing clip {i+1}/{len(workout_plan)}: {exercise['name']} ({exercise.get('length', 0)}s)")
        start_time, end_time = current_time, current_time + exercise.get('length', 0)
        
        if end_time > base_video.duration: end_time = base_video.duration
        if start_time >= end_time: continue
            
        video_subclip = base_video.subclipped(start_time, end_time)
        clips_to_composite = [video_subclip]

        # TextClip is reliable for simple, static text.
        exercise_name_text = TextClip(
            text=exercise['name'].upper(),
            font=FONT_FILE, font_size=60, color=FONT_COLOR,
            stroke_color=TEXT_STROKE_COLOR, stroke_width=TEXT_STROKE_WIDTH, margin=(15, 15)
        ).with_position(('left', 'top')).with_duration(video_subclip.duration)
        clips_to_composite.append(exercise_name_text)
        
        # Use a custom Pillow-based function for the dynamic countdown to ensure reliability and perfect centering.
        def make_countdown_frame(t, subclip_duration=video_subclip.duration):
            time_left = max(0, floor(subclip_duration - t))
            text_to_draw = str(time_left)

            # Create a black canvas with Pillow
            canvas = Image.new('RGB', countdown_size, 'black')
            draw = ImageDraw.Draw(canvas)

            # Calculate the center point of the canvas
            center_x = countdown_size[0] / 2
            center_y = countdown_size[1] / 2

            # Use the 'anchor="mm"' argument to tell Pillow to use our (x,y) coordinate
            # as the middle-middle point for perfect visual centering of the text.
            draw.text(
                (center_x, center_y),
                text_to_draw,
                font=pillow_font,
                anchor="mm", # Use Middle-Middle anchor
                fill=FONT_COLOR,
                stroke_width=TEXT_STROKE_WIDTH,
                stroke_fill=TEXT_STROKE_COLOR
            )
            
            # Convert the Pillow image to a NumPy array for MoviePy
            return np.array(canvas)

        countdown_pos = (base_video.w - countdown_size[0], 0)
        
        countdown_clip = VideoClip(make_countdown_frame, duration=video_subclip.duration).with_position(countdown_pos)
        clips_to_composite.append(countdown_clip)
        
        if exercise.get('type') not in ['warmup', 'cool down', 'rest']:
            def make_progress_bar_frame(t, captured_start_time=start_time):
                warmup_duration = workout_plan[0].get('length', 0) if workout_plan and workout_plan[0].get('type') == 'warmup' else 0
                time_elapsed = captured_start_time + t - warmup_duration
                progress = max(0, time_elapsed / total_workout_duration) if total_workout_duration > 0 else 0
                
                w, h = int(base_video.w), 15
                bar_w = int(w * progress)

                bar_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(bar_img)
                draw.rectangle([(0, 0), (w, h)], fill=(50, 50, 50, 255))
                draw.rectangle([(0, 0), (bar_w, h)], fill=(255, 165, 0, 255))
                
                return np.array(bar_img)
            
            progress_bar_clip = VideoClip(make_progress_bar_frame, duration=video_subclip.duration).with_position(('center', 'bottom'))
            clips_to_composite.append(progress_bar_clip)
            
        if i + 1 < len(workout_plan):
            next_exercise = workout_plan[i+1]
            if next_exercise['name'].lower() not in ['rest', 'cool down']:
                next_start_time = end_time
                if next_start_time < base_video.duration:
                    preview_clip = base_video.subclipped(next_start_time, min(next_start_time + 5, base_video.duration)).with_fps(15)
                    pip_width = base_video.w * 0.25
                    preview_clip_resized = preview_clip.resized(width=pip_width)
                    next_up_text = TextClip(
                        text="NEXT UP:",
                        font=FONT_FILE,
                        font_size=30,
                        color='white',
                        stroke_color='black',
                        stroke_width=1
                    )
                    text_bg = ColorClip(size=(int(next_up_text.w * 1.1), int(next_up_text.h * 1.2)), color=(0,0,0)).with_opacity(0.6)
                    text_with_bg = CompositeVideoClip([text_bg, next_up_text.with_position('center')])
                    next_up_group = CompositeVideoClip([preview_clip_resized, text_with_bg.with_position(('center', 0.05), relative=True)], size=preview_clip_resized.size)
                    
                    base_pip = (next_up_group
                                 .with_start(max(0, video_subclip.duration - 10))
                                 .with_duration(10)
                                 .with_position((0.97, 0.95), relative=True))
                    
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
    parser.add_argument('-t', '--test', action='store_true', help="Enable test mode for fast, low-quality rendering.")
    parser.add_argument('--gpu', action='store_true', help="Attempt to use GPU hardware acceleration for encoding.")
    
    args = parser.parse_args()
    create_workout_video(args.yaml, args.input, args.output, args.test, args.gpu)