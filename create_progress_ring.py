import os
import sys
import yaml
import random
import argparse
import subprocess
import shutil
from PIL import Image, ImageDraw, ImageFont

# --- Helper Functions ---

def generate_base_color():
    """Returns a random, saturated color that is not too close to white."""
    return (random.randint(20, 180), random.randint(20, 180), random.randint(20, 180))

def lerp(start, end, t):
    """Linearly interpolates between two values."""
    return start + (end - start) * t

def lerp_color(start_color, end_color, progress):
    """Linearly interpolates between two RGB colors."""
    r = int(lerp(start_color[0], end_color[0], progress))
    g = int(lerp(start_color[1], end_color[1], progress))
    b = int(lerp(start_color[2], end_color[2], progress))
    return (r, g, b)

def parse_color_with_alpha(color_str):
    """Parses a color string like 'black@0.7' into an RGBA tuple."""
    color_map = {'black': (0,0,0), 'white': (255,255,255)} # Extend as needed
    if '@' in color_str:
        name, alpha_str = color_str.split('@')
        rgb = color_map.get(name.lower(), (0,0,0))
        alpha = int(float(alpha_str) * 255)
        return rgb + (alpha,)
    else:
        # Return fully opaque color if no alpha is specified
        return color_map.get(color_str.lower(), (0,0,0)) + (255,)

def draw_ring_segment(draw, box, start_angle, end_angle, color, width):
    """Draws a single arc segment of the ring."""
    draw.arc(box, start=start_angle, end=end_angle + 0.5, fill=color, width=width)

def draw_countdown_text(draw, center_xy, remaining_seconds, font, **kwargs):
    """Draws the centered countdown text with a stroke for legibility."""
    text = f"{remaining_seconds}"
    stroke_width = kwargs.get('stroke_width', 2)
    stroke_color = kwargs.get('stroke_color', (0,0,0))
    fill_color = kwargs.get('fill_color', (255,255,255))
    x, y = center_xy
    # Draw stroke by offsetting text in a small grid
    for i in range(-stroke_width, stroke_width + 1):
        for j in range(-stroke_width, stroke_width + 1):
            if i != 0 or j != 0: # Don't draw in the center
                draw.text((x+i, y+j), text, font=font, fill=stroke_color, anchor="mm")
    # Draw the main text on top
    draw.text(center_xy, text, font=font, fill=fill_color, anchor="mm")

# --- Main Program Logic (Optimized and Corrected) ---

def create_progress_ring(
    cfg: dict, 
    duration: int, 
    output_folder: str
):
    """Generates a complete progress ring asset, including PNGs, video, and cleanup."""
    
    print("--- Starting PNG Frame Generation ---")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # --- Load settings from config dictionary ---
    fps = cfg['fps']
    direction = cfg['direction']
    stroke_width = cfg['stroke_width']
    border_width = cfg['border_width']
    size = cfg['size']
    no_text = cfg.get('no_text', False)
    
    font_cfg = cfg['text']
    font_style = font_cfg['font_style']
    text_stroke_width = font_cfg['stroke_width']
    hide_on_zero = font_cfg.get('hide_on_zero', True)
    font_path = font_cfg['font_file']
    
    circle_cfg = font_cfg.get('background_circle', {'enabled': False})
    circle_enabled = circle_cfg.get('enabled', False)
    circle_padding = circle_cfg.get('padding', 0)

    # --- Font Loading ---
    used_font = None
    if not no_text:
        try:
            # CORRECTED: Font size calculation is now based on the final circle size
            total_visible_width = stroke_width + (border_width * 2)
            outer_margin = 4
            inner_space_radius = (size / 2) - outer_margin - total_visible_width
            # The usable diameter for text is the inner space, minus padding on both sides
            usable_text_diameter = (inner_space_radius - circle_padding) * 2
            calculated_font_size = int(usable_text_diameter * font_cfg['font_size_ratio'])

            used_font = ImageFont.truetype(font_path, calculated_font_size)
            print(f"Successfully loaded font: {font_path}")
            if font_style and hasattr(used_font, 'get_variation_names'):
                target_style_b = font_style.encode('utf-8')
                if target_style_b in used_font.get_variation_names():
                    used_font.set_variation_by_name(target_style_b)
                    print(f"-> Set font style to: '{font_style}'")
        except IOError:
            print(f"Warning: Font not found at '{font_path}'. Falling back to default.")
            used_font = ImageFont.load_default()
            
    # --- Color & Geometry Setup ---
    start_color = generate_base_color()
    end_color = (255, 255, 255)
    print(f"Gradient Start Color (RGB): {start_color}")
    
    center_point = (size // 2, size // 2)
    total_frames = duration * fps
    angle_per_frame = 360 / total_frames
    
    # Create the persistent canvas for the ring animation
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw_on_canvas = ImageDraw.Draw(canvas)

    print(f"Configuration: {duration}s @ {fps}fps, Size={size}px, RingStroke={stroke_width}px, Border={border_width}px")

    # --- Frame Generation Loop ---
    for i in range(total_frames):
        # Draw one new ring segment onto the persistent canvas
        progress = i / total_frames
        color = lerp_color(start_color, end_color, progress)
        start_angle_offset = -90
        segment_start_angle = start_angle_offset + (i * angle_per_frame * (1 if direction == 'clockwise' else -1))
        segment_end_angle = segment_start_angle + (angle_per_frame * (1 if direction == 'clockwise' else -1))
        
        # Explicit Bounding Boxes for pixel-perfect layers
        outer_margin = 4
        box_outer = (outer_margin, outer_margin, size - outer_margin, size - outer_margin)
        margin_color = outer_margin + border_width
        box_color = (margin_color, margin_color, size - margin_color, size - margin_color)
        margin_inner = outer_margin + border_width + stroke_width
        box_inner = (margin_inner, margin_inner, size - margin_inner, size - margin_inner)
        
        # Draw layers of the new segment
        if border_width > 0:
            draw_ring_segment(draw_on_canvas, box_outer, segment_start_angle, segment_end_angle, 'black', border_width)
        draw_ring_segment(draw_on_canvas, box_color, segment_start_angle, segment_end_angle, color, stroke_width)
        if border_width > 0:
            draw_ring_segment(draw_on_canvas, box_inner, segment_start_angle, segment_end_angle, 'black', border_width)
        
        # Copy the canvas with the updated ring to a temporary image
        frame_image = canvas.copy()
        
        # Get a draw context for the temporary image
        draw_on_frame = ImageDraw.Draw(frame_image)
        
        # Draw background circle if enabled
        if not no_text and circle_enabled:
            # CORRECTED: Calculate radius to be perfectly flush with the ring's inner border
            total_ring_width = stroke_width + (border_width * 2)
            circle_radius = (size / 2) - outer_margin - total_ring_width
            
            circle_layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw_on_circle = ImageDraw.Draw(circle_layer)
            cx, cy = center_point
            box = (cx - circle_radius, cy - circle_radius, cx + circle_radius, cy + circle_radius)
            circle_color = parse_color_with_alpha(circle_cfg.get('color', 'black@0.7'))
            draw_on_circle.ellipse(box, fill=circle_color)
            frame_image.alpha_composite(circle_layer)
        
        # Draw countdown text on top of all other layers
        if not no_text:
            remaining_seconds = duration - (i // fps)
            if hide_on_zero and remaining_seconds > 0:
                draw_countdown_text(draw_on_frame, center_point, remaining_seconds, used_font, stroke_width=text_stroke_width)
            elif not hide_on_zero and remaining_seconds >= 0:
                draw_countdown_text(draw_on_frame, center_point, remaining_seconds, used_font, stroke_width=text_stroke_width)
        
        # Save the final composed frame
        frame_path = os.path.join(output_folder, f'frame_{i:05d}.png')
        frame_image.save(frame_path)

        sys.stdout.write(f"\r-> Generating frame {i+1}/{total_frames} ({int((i+1)/total_frames*100)}%)")
        sys.stdout.flush()

    print("\n--- PNG Frame Generation Complete ---")

# --- Main Execution Block ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a progress ring asset using a config.yaml file.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('duration', type=int, help='Duration of the timer in seconds.')
    parser.add_argument('--config', type=str, default='config.yaml', help='Path to the configuration YAML file.')
    
    args = parser.parse_args()

    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found at '{args.config}'")
        sys.exit(1)
        
    ring_cfg = config['progress_ring']
    paths_cfg = config['paths']
    
    # Define paths
    output_dir = os.path.join(paths_cfg['asset_output_dir'], paths_cfg['timers_subdir'])
    png_sequence_folder = os.path.join(output_dir, f'temp_frames_{args.duration}s')
    final_video_path = os.path.join(output_dir, f'timer_{args.duration}s.mov')
    
    # Step 1: Generate the PNG frames
    create_progress_ring(
        cfg=ring_cfg, 
        duration=args.duration,
        output_folder=png_sequence_folder
    )

    # Step 2: Assemble frames into ProRes video using FFmpeg
    print("\n--- Assembling ProRes Video ---")
    ffmpeg_cmd = [
        'ffmpeg', '-framerate', str(ring_cfg["fps"]),
        '-i', os.path.join(png_sequence_folder, 'frame_%05d.png'),
        '-c:v', 'prores_aw', '-pix_fmt', 'yuva444p10le', '-y',
        final_video_path
    ]
    
    try:
        # Run FFmpeg, check for errors, and hide verbose output
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"Successfully created video: {final_video_path}")
    except subprocess.CalledProcessError as e:
        print("\n--- FFmpeg command failed! ---")
        print("Command:", " ".join(e.cmd))
        print("FFmpeg output (stderr):\n", e.stderr.decode())
        sys.exit(1)
        
    # Step 3: Clean up the temporary PNG frames
    print("\n--- Cleaning up temporary files ---")
    try:
        shutil.rmtree(png_sequence_folder)
        print(f"Successfully deleted temporary folder: {png_sequence_folder}")
    except OSError as e:
        print(f"Error deleting temporary folder: {e}")
        
    print(f"\n✅ Asset generation complete for {args.duration}s timer.")