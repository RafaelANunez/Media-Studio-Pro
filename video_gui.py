import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from moviepy import *
import os
import subprocess
import time
import threading
import json 
import math
import ctypes
import re
from PIL import Image
from proglog import ProgressBarLogger

# --- TRY IMPORTING VLC ---
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    print("Warning: 'python-vlc' not found. Fullscreen performance will be limited.")

# --- TRY IMPORTING TKINTERDND2 (For Drag & Drop) ---
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    print("Warning: 'tkinterdnd2' not found. Drag and drop disabled. (pip install tkinterdnd2)")

    # Dummy class to prevent crash if library is missing
    class TkinterDnD:
        class DnDWrapper:
            pass

# --- 1. Custom Logger for Progress Bar ---

class TkProgressBarLogger(ProgressBarLogger):
    def __init__(self, update_callback):
        super().__init__(init_state=None, bars=None, ignored_bars=None, logged_bars='all', min_time_interval=0, ignore_bars_under=0)
        self.update_callback = update_callback

    def bars_callback(self, bar, attr, value, old_value=None):
        if bar == 't' and attr == 'index':
            if 'total' in self.bars[bar]:
                total = self.bars[bar]['total']
                if total > 0:
                    percentage = value / total
                    self.update_callback(percentage)

# --- 2. Backend Video Logic ---

def combine_video_clips_backend(input_files, output_path, logger=None):
    if not input_files: return None
    try:
        clips = []
        for f in input_files:
            if not os.path.exists(f): return None
            clips.append(VideoFileClip(f))
        
        final_clip = concatenate_videoclips(clips, method="compose")
        
        final_clip.write_videofile(
            output_path, 
            codec='libx264', 
            audio_codec='aac', 
            temp_audiofile='temp-audio.m4a', 
            remove_temp=True, 
            preset='ultrafast',
            threads=4,
            logger=logger 
        )

        for clip in clips: clip.close()
        return os.path.abspath(output_path)
    except Exception as e:
        raise e

def convert_to_gif_backend(video_path, output_path, fps=10, scale=0.5, speed=1.0, logger=None):
    try:
        clip = VideoFileClip(video_path)
        if speed != 1.0: clip = clip.with_speed_scaled(speed)
        if scale != 1.0: clip = clip.resized(scale)
        clip.write_gif(output_path, fps=fps, logger=logger)
        clip.close()
        return True
    except Exception as e:
        print(f"GIF Error: {e}")
        return False
    
def universal_convert_backend(input_path, output_path, quality="High", speed="Medium", logger=None):
    """
    Backend with Speed/Preset control.
    speed options: "Ultrafast", "Fast", "Medium", "Slow"
    """
    import subprocess
    from PIL import Image
    
    input_ext = os.path.splitext(input_path)[1].lower()
    output_ext = os.path.splitext(output_path)[1].lower()
    image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.ico']
    
    # --- 1. IMAGE MODE ---
    if input_ext in image_exts:
        try:
            img = Image.open(input_path)
            if output_ext in ['.jpg', '.jpeg', '.bmp'] and img.mode in ('RGBA', 'LA'):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            
            q_val = 100 if quality == "High" else (85 if quality == "Medium" else 60)
            if output_ext == '.ico': img.save(output_path, format='ICO', sizes=[(256, 256)])
            else: img.save(output_path, quality=q_val)
            return True, "Success"
        except Exception as e:
            return False, f"Image Error: {e}"

    # --- 2. VIDEO MODE ---
    if output_ext == ".gif":
        try:
            fps = 15 if quality == "High" else 10
            scale = 1.0 if quality == "High" else 0.5
            convert_to_gif_backend(input_path, output_path, fps=fps, scale=scale)
            return True, "Success"
        except Exception as e:
            return False, f"GIF Error: {e}"

    ffmpeg_cmd = "ffmpeg"
    cmd = [ffmpeg_cmd, "-y", "-i", input_path]

    # --- SPEED & QUALITY SETTINGS ---
    # Map UI Speed to FFmpeg Presets
    preset_map = {
        "Ultrafast": "ultrafast", # Fastest encoding, larger file
        "Fast": "fast",
        "Medium": "medium",
        "Slow": "slow"            # Best compression, slowest
    }
    preset = preset_map.get(speed, "medium")
    
    crf = "18" if quality == "High" else ("23" if quality == "Medium" else "28")

    # Audio Extraction
    if output_ext in ['.mp3', '.wav', '.m4a']:
        cmd.extend(["-vn", "-map", "a"]) 
        if output_ext == '.mp3': cmd.extend(["-c:a", "libmp3lame", "-q:a", "2" if quality=="High" else "5"])
        elif output_ext == '.m4a': cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    # Video Conversion
    else:
        if output_ext == '.webm':
            cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
        else:
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", preset, "-crf", crf])
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    cmd.append(output_path)

    # Execution
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return False, f"FFmpeg Error:\n{stderr[-300:]}"

        if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
            return False, "File created but is empty (0 bytes)."

        return True, "Success"
    except FileNotFoundError:
        return False, "FFmpeg.exe not found."
    except Exception as e:
        return False, f"General Error: {e}"

def resize_clip_backend(input_path, width, height, output_path, mode="stretch", anchor="center", logger=None):
    """
    Resizes video.
    mode: "stretch" (distort), "fit" (black bars), "crop" (fill screen/cut edges)
    anchor: "center", "top-left", "bottom-right" (only used for 'crop')
    """
    try:
        # --- FFmpeg Command Generation ---
        ffmpeg_cmd = "ffmpeg"
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        filter_str = ""

        if mode == "stretch":
            # Simple stretch (distorts image)
            filter_str = f"scale={width}:{height}"

        elif mode == "fit":
            # Fit inside + Black Bars (Letterbox)
            # 1. Scale to fit inside box
            # 2. Pad to fill box, centering the video
            filter_str = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            )

        elif mode == "crop":
            # Crop to Fill (Zoom + Cut)
            # 1. Scale so the SMALLEST dimension matches target (filling the box)
            # 2. Crop the excess
            
            # Step 1: Scale (force_original_aspect_ratio=increase ensures we fill the box)
            scale_part = f"scale={width}:{height}:force_original_aspect_ratio=increase"
            
            # Step 2: Crop
            if anchor == "top-left":
                # Crop from top-left (0,0)
                crop_part = f"crop={width}:{height}:0:0"
            elif anchor == "bottom-right":
                # Crop from bottom-right (w-new_w, h-new_h)
                # 'in_w' and 'in_h' refer to the size AFTER the scale filter
                crop_part = f"crop={width}:{height}:in_w-{width}:in_h-{height}"
            else: # center
                # Crop from center
                crop_part = f"crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2"
            
            filter_str = f"{scale_part},{crop_part}"

        cmd = [
            ffmpeg_cmd, "-y",               
            "-i", input_path,               
            "-vf", filter_str, 
            "-c:v", "libx264",              
            "-preset", "ultrafast",         
            "-crf", "23",                   
            "-c:a", "copy",                 
            output_path
        ]
        
        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return output_path

    except Exception as e:
        print(f"Direct FFmpeg failed ({e}). Switching to MoviePy fallback...")
        
        # --- MoviePy Fallback ---
        try:
            clip = VideoFileClip(input_path)
            
            if mode == "stretch":
                new_clip = clip.resized(new_size=(width, height))
            
            elif mode == "fit":
                # Fit logic (as before)
                ratio_w = width / clip.w
                ratio_h = height / clip.h
                scale_factor = min(ratio_w, ratio_h)
                resized = clip.resized(scale=scale_factor)
                new_clip = CompositeVideoClip(
                    [resized.with_position("center")], 
                    size=(width, height), bg_color=(0,0,0)
                )
            
            elif mode == "crop":
                # Crop to Fill logic
                ratio_w = width / clip.w
                ratio_h = height / clip.h
                scale_factor = max(ratio_w, ratio_h) # Scale up to fill
                
                resized = clip.resized(scale=scale_factor)
                
                # Calculate Crop Box
                x1, y1 = 0, 0
                if anchor == "center":
                    x1 = (resized.w - width) / 2
                    y1 = (resized.h - height) / 2
                elif anchor == "bottom-right":
                    x1 = resized.w - width
                    y1 = resized.h - height
                # top-left is 0,0
                
                new_clip = resized.cropped(x1=x1, y1=y1, width=width, height=height)

            new_clip.write_videofile(
                output_path, 
                codec='libx264', audio_codec='aac', temp_audiofile='temp-audio-resize.m4a', 
                remove_temp=True, preset='ultrafast', logger=logger
            )
            clip.close()
            new_clip.close()
            return output_path
            
        except Exception as e2:
            raise e2

def upscale_media_backend(input_path, output_path, scale_factor, width=None, height=None, algo="lanczos", sharpen=True):
    try:
        ffmpeg_cmd = "ffmpeg"
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        scale_filter = ""
        if width and height:
            scale_filter = f"scale={width}:{height}:flags={algo}"
        else:
            scale_filter = f"scale=iw*{scale_factor}:ih*{scale_factor}:flags={algo}"
            
        if sharpen:
            scale_filter += ",unsharp=5:5:1.0:5:5:0.0"

        cmd = [ffmpeg_cmd, "-y", "-i", input_path, "-vf", scale_filter]
        
        ext = os.path.splitext(output_path)[1].lower()
        if ext in ['.jpg', '.png', '.bmp']:
            cmd.extend(["-q:v", "2"]) 
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-c:a", "copy"])
            
        cmd.append(output_path)
        
        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return output_path
    except Exception as e:
        raise e

def upscale_with_ai_backend(input_path, output_path, scale_factor, logger=None, enhance_faces=False, exe_dir=None, tile_size=0):
    exe_name = "realesrgan-ncnn-vulkan.exe" if os.name == 'nt' else "realesrgan-ncnn-vulkan"
    
    if exe_dir and os.path.exists(os.path.join(exe_dir, exe_name)):
        exe_path = os.path.join(exe_dir, exe_name)
    else:
        exe_path = os.path.abspath(exe_name)
    
    if not os.path.exists(exe_path):
        return False, f"Executable not found at: {exe_path}. Please set the correct path in Settings."

    ext = os.path.splitext(input_path)[1].lower()
    is_image = ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff']

    def run_ai_command(in_file, out_file, model, safe_mode=False):
        cmd = [
            exe_path,
            "-i", in_file,
            "-o", out_file,
            "-n", model,
            "-s", str(scale_factor),
            "-f", "jpg"
        ]
        
        if tile_size > 0:
            cmd.extend(["-t", str(tile_size)])
            if tile_size >= 400:
                cmd.extend(["-j", "2:2:2"]) 
            else:
                cmd.extend(["-j", "1:2:2"])
        elif safe_mode:
            cmd.extend(["-t", "64", "-j", "1:1:1"])
        else:
            cmd.extend(["-t", "256", "-j", "1:2:2"])

        print(f"AI Command (Safe={safe_mode}, Tile={tile_size}):", " ".join(cmd))
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if is_image:
        try:
            if logger: logger(0.1)
            
            if tile_size > 0:
                run_ai_command(input_path, output_path, "realesrgan-x4plus", safe_mode=False)
            else:
                try:
                    run_ai_command(input_path, output_path, "realesrgan-x4plus", safe_mode=False)
                except subprocess.CalledProcessError:
                    print("Standard AI crashed. Retrying in Safe Mode...")
                    if logger: logger(0.2)
                    run_ai_command(input_path, output_path, "realesr-animevideov3", safe_mode=True)

            if logger: logger(0.5)

            if enhance_faces:
                bat_name = "run_codeformer.bat"
                codeformer_cmd = None
                if exe_dir and os.path.exists(os.path.join(exe_dir, bat_name)):
                    codeformer_cmd = os.path.join(exe_dir, bat_name)
                elif os.path.exists(os.path.abspath(bat_name)):
                    codeformer_cmd = os.path.abspath(bat_name)

                if codeformer_cmd:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    subprocess.run([codeformer_cmd, output_path], check=True, startupinfo=startupinfo)

            if logger: logger(1.0)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True, "Success"
            else:
                return False, "AI failed to generate output file."

        except Exception as e:
            return False, f"Image Upscale Error: {str(e)}"

    else:
        temp_dir = f"TEMP_AI_{int(time.time())}"
        in_frames = os.path.join(temp_dir, "input")
        out_frames = os.path.join(temp_dir, "output")
        final_frames = out_frames
        
        os.makedirs(in_frames, exist_ok=True)
        os.makedirs(out_frames, exist_ok=True)

        try:
            if logger: logger(0.1)
            
            subprocess.run([
                "ffmpeg", "-i", input_path, 
                "-q:v", "2", 
                os.path.join(in_frames, "frame_%08d.jpg")
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if logger: logger(0.2)
            
            if tile_size > 0:
                 run_ai_command(in_frames, out_frames, "realesr-animevideov3", safe_mode=False)
            else:
                try:
                    run_ai_command(in_frames, out_frames, "realesr-animevideov3", safe_mode=False)
                except subprocess.CalledProcessError:
                    print("Video AI crashed. Retrying in Safe Mode...")
                    run_ai_command(in_frames, out_frames, "realesr-animevideov3", safe_mode=True)

            if logger: logger(0.7)

            bat_name = "run_codeformer.bat"
            codeformer_cmd = None
            if exe_dir and os.path.exists(os.path.join(exe_dir, bat_name)):
                 codeformer_cmd = os.path.join(exe_dir, bat_name)
            elif os.path.exists(os.path.abspath(bat_name)):
                 codeformer_cmd = os.path.abspath(bat_name)

            if enhance_faces and codeformer_cmd:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.run([codeformer_cmd, out_frames], check=True, startupinfo=startupinfo)

            audio_path = os.path.join(temp_dir, "audio.m4a")
            has_audio = False
            try:
                subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "copy", audio_path], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                    has_audio = True
            except: pass

            fps = 30
            try:
                clip = VideoFileClip(input_path)
                fps = clip.fps
                clip.close()
            except: pass

            combine_cmd = [
                "ffmpeg", "-y", "-framerate", str(fps),
                "-i", os.path.join(final_frames, "frame_%08d.jpg"),
            ]
            
            if has_audio: combine_cmd.extend(["-i", audio_path])
            
            combine_cmd.extend([
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-c:a", "aac" if has_audio else "copy",
                output_path
            ])
            
            if has_audio:
                combine_cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(combine_cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if logger: logger(1.0)
            return True, "Success"

        except Exception as e:
            return False, f"Video Upscale Error: {str(e)}"
        finally:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except: pass

def interpolate_video_backend(input_path, output_path, method="ffmpeg", target_fps=60, multiplier=2, logger=None, exe_dir=None):
    try:
        if method == "ffmpeg":
            filter_str = f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
            
            cmd = [
                "ffmpeg", "-y", 
                "-i", input_path,
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "copy",
                output_path
            ]
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return True, "Success"

        elif method == "rife":
            exe_name = "rife-ncnn-vulkan.exe" if os.name == 'nt' else "rife-ncnn-vulkan"
            
            if exe_dir and os.path.exists(os.path.join(exe_dir, exe_name)):
                exe_path = os.path.join(exe_dir, exe_name)
            else:
                exe_path = os.path.abspath(exe_name)

            if not os.path.exists(exe_path):
                return False, f"RIFE Executable not found at: {exe_path}. Please set path in Settings."

            temp_dir = f"TEMP_RIFE_{int(time.time())}"
            in_frames = os.path.join(temp_dir, "input")
            out_frames = os.path.join(temp_dir, "output")
            os.makedirs(in_frames, exist_ok=True)
            os.makedirs(out_frames, exist_ok=True)

            try:
                if logger: logger(0.1)
                
                # Extract frames
                subprocess.run([
                    "ffmpeg", "-i", input_path, 
                    os.path.join(in_frames, "frame_%08d.png")
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if logger: logger(0.2)

                # --- RIFE LOOP FOR MULTIPLIER (2x, 4x) ---
                import shutil
                current_mult = 1
                target_mult = multiplier if multiplier in [2, 4] else 2
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                while current_mult < target_mult:
                    # Run RIFE (Input -> Output)
                    cmd = [exe_path, "-i", in_frames, "-o", out_frames]
                    subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    
                    current_mult *= 2
                    
                    # If we need another pass (e.g. going to 4x), move Output back to Input
                    if current_mult < target_mult:
                        # Clear Input
                        for f in os.listdir(in_frames):
                            os.remove(os.path.join(in_frames, f))
                        # Move Output to Input
                        for f in os.listdir(out_frames):
                            shutil.move(os.path.join(out_frames, f), os.path.join(in_frames, f))

                if logger: logger(0.8)

                # Calculate new FPS
                orig_fps = 30
                try:
                    clip = VideoFileClip(input_path)
                    orig_fps = clip.fps if clip.fps else 30
                    clip.close()
                except: pass
                
                new_fps = orig_fps * target_mult

                # Handle Audio
                audio_path = os.path.join(temp_dir, "audio.m4a")
                has_audio = False
                try:
                    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "copy", audio_path], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                        has_audio = True
                except: pass

                # Recombine
                combine_cmd = [
                    "ffmpeg", "-y", "-framerate", str(new_fps),
                    "-i", os.path.join(out_frames, "%08d.png"), 
                ]
                
                if has_audio: combine_cmd.extend(["-i", audio_path])
                
                combine_cmd.extend([
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-c:a", "aac" if has_audio else "copy",
                    output_path
                ])
                
                if has_audio:
                    combine_cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

                subprocess.run(combine_cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if logger: logger(1.0)
                return True, "Success"

            except Exception as e:
                return False, f"RIFE Error: {str(e)}"
            finally:
                import shutil
                try: shutil.rmtree(temp_dir)
                except: pass

    except Exception as e:
        return False, str(e)

def crop_video_backend(video_path, start_time, end_time, output_path):
    duration = end_time - start_time
    if duration <= 0: return None
    try:
        ffmpeg_cmd = "ffmpeg"
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        cmd = [
            ffmpeg_cmd, "-y", "-ss", str(start_time), "-i", video_path, "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", output_path
        ]
        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return output_path
    except Exception:
        pass

    try:
        clip = VideoFileClip(video_path)
        trimmed = clip.subclipped(start_time, end_time)
        trimmed.write_videofile(output_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, preset='ultrafast')
        clip.close(); trimmed.close()
        return output_path
    except Exception as e:
        raise e

def extract_frame_backend(video_path, time_in_seconds, output_path):
    # Safety margin: If we are at the very end, step back slightly to capture the actual last frame.
    # We do this calculation before running FFmpeg or MoviePy.
    try:
        # Quick probe to get duration/fps without full load (optional, but safer to use hard logic)
        # We'll rely on the Fallback block for precise FPS math, but for FFmpeg CLI, 
        # just subtracting 0.1s is usually enough to save the last frame safezone.
        pass 
    except: pass

    # --- FIX: LOGIC TO PREVENT OVERSHOOTING DURATION ---
    # We will refine 'time_in_seconds' inside the blocks below.

    # 1. Try Direct FFmpeg
    try:
        ffmpeg_cmd = "ffmpeg"
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        # If we are effectively at 0 (start), keep it. 
        # If we are > 0, we trust the time, but if it fails, we fall back to MoviePy which has the smart fix below.
        
        cmd = [ffmpeg_cmd, "-y", "-ss", str(time_in_seconds), "-i", video_path, "-frames:v", "1", "-q:v", "2", output_path]
        subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # Check if FFmpeg actually created a valid file (size > 0)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        else:
            # If FFmpeg made an empty file (common at end of video), delete and fallback
            if os.path.exists(output_path): os.remove(output_path)
            raise Exception("FFmpeg produced empty file")

    except Exception:
        pass # Switch to MoviePy fallback

    # 2. MoviePy Fallback (With The Fix)
    try:
        clip = VideoFileClip(video_path)
        
        # --- THE FIX IS HERE ---
        # If the requested time is very close to (or past) the end, shift back by 1 frame.
        total_dur = clip.duration
        t = time_in_seconds

        if t >= total_dur - 0.05:
            # Calculate duration of a single frame
            frame_dur = (1.0 / clip.fps) if (clip.fps and clip.fps > 0) else 0.05
            # Set time to (Duration - 1 Frame) to ensure we hit valid data
            t = max(0, total_dur - frame_dur)
        
        # Clamp t to be safe regardless
        t = min(t, total_dur - 0.01)
        if t < 0: t = 0
            
        clip.save_frame(output_path, t=t)
        clip.close()
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed: {e}")
        return False

# --- Helper Utils ---

def get_file_size_string(path):
    try:
        size_bytes = os.path.getsize(path)
        if size_bytes == 0: return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])
    except: return "Unknown"

def extract_clip_metadata(video_path, thumb_height=60):
    data = {"thumb": None, "duration": 0, "resolution": (0, 0), "fps": 0, "size_str": get_file_size_string(video_path)}
    try:
        clip = VideoFileClip(video_path)
        data["duration"] = clip.duration
        data["resolution"] = clip.size
        data["fps"] = clip.fps
        if clip.duration > 0:
            t = 1 if clip.duration > 1 else 0
            frame = clip.get_frame(t)
            img = Image.fromarray(frame)
            aspect_ratio = img.width / img.height
            new_width = int(thumb_height * aspect_ratio)
            data["thumb"] = ctk.CTkImage(light_image=img, dark_image=img, size=(new_width, thumb_height))
        clip.close()
    except Exception as e:
        print(f"Metadata Error: {e}")
    return data

def get_preview_pil_images(video_path, duration=3.0, fps=8, height=250):
    pil_images = []
    clip = None
    try:
        clip = VideoFileClip(video_path, audio=False)
        max_duration = min(duration, clip.duration)
        total_frames = int(max_duration * fps)
        if total_frames < 1: total_frames = 1
        step = 1.0 / fps
        for i in range(total_frames):
            t = i * step
            if t > clip.duration: break
            frame_data = clip.get_frame(t)
            img = Image.fromarray(frame_data).copy()
            aspect = img.width / img.height
            new_width = int(height * aspect)
            img = img.resize((new_width, height), Image.Resampling.LANCZOS)
            pil_images.append(img)
        return pil_images, int(step * 1000)
    except Exception as e:
        print(f"Loader Error: {e}")
        return [], 100
    finally:
        if clip:
            try: clip.close()
            except: pass

def delete_section_backend(video_path, start_remove, end_remove, output_path):
    try:
        clip = VideoFileClip(video_path)
        if start_remove <= 0:
            final = clip.subclipped(end_remove, clip.duration)
        elif end_remove >= clip.duration:
            final = clip.subclipped(0, start_remove)
        else:
            clip1 = clip.subclipped(0, start_remove)
            clip2 = clip.subclipped(end_remove, clip.duration)
            final = concatenate_videoclips([clip1, clip2])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, preset='ultrafast')
        clip.close(); final.close()
        return output_path
    except Exception as e:
        raise e

def insert_clip_backend(main_video_path, insert_video_path, insert_time, output_path):
    try:
        main = VideoFileClip(main_video_path)
        insert = VideoFileClip(insert_video_path)
        if insert_time <= 0: final = concatenate_videoclips([insert, main])
        elif insert_time >= main.duration: final = concatenate_videoclips([main, insert])
        else:
            part1 = main.subclipped(0, insert_time)
            part2 = main.subclipped(insert_time, main.duration)
            final = concatenate_videoclips([part1, insert, part2])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, preset='ultrafast')
        main.close(); insert.close(); final.close()
        return output_path
    except Exception as e:
        raise e

# --- 3. Advanced Editor Popup ---

class VideoEditorPopup(ctk.CTkToplevel):
    def __init__(self, parent, video_path, mode="extract", callback=None, defaults=None, start_fullscreen=False, use_vlc=True, scale_factor=1.0, editor_height=600):
        super().__init__(parent)
        self.mode = mode
        self.callback = callback
        self.original_video_path = video_path 
        self.current_video_path = video_path
        self.defaults = defaults
        self.parent_window = parent
        self.use_vlc_fullscreen = use_vlc and VLC_AVAILABLE
        self.use_vlc_always = (self.mode == "view") and self.use_vlc_fullscreen
        
        self.scale_factor = scale_factor 
        self.editor_height = editor_height  
        self.temp_files = []
        
        title = "🖼️ Extract Frame" if mode == "extract" else ("✂️ Advanced Editor" if mode == "trim" else "📺 Preview Merged Video")
        self.title(title)
        
        base_h = self.editor_height + 150
        base_w = int(base_h * 1.33) 
        self.width = int(base_w * self.scale_factor)
        self.height = int(base_h * self.scale_factor)
        self._center_window_top()
        
        self.transient(parent)
        self.grab_set()
        self.lift()
        self.after(100, lambda: self.focus_force())
        
        # State
        self.is_playing = False
        self.playback_speed = 1.0
        self.last_frame_time = 0.0
        self.current_time = 0.0
        self.duration = 0.0
        self.start_time = 0.0
        self.end_time = 0.0
        self.is_fullscreen = False
        self.controls_visible = True
        self.is_zoomed = False  
        self.hide_task = None 
        self.active_engine = "moviepy"
        
        # VLC Setup
        self.vlc_instance = None
        self.vlc_player = None
        if self.use_vlc_fullscreen:
            try:
                self.vlc_instance = vlc.Instance("--no-xlib --no-video-title-show --quiet")
                self.vlc_player = self.vlc_instance.media_player_new()
                self.vlc_player.video_set_mouse_input(False)
                self.vlc_player.video_set_key_input(False)
            except Exception as e:
                print(f"VLC Init Error: {e}")
                self.use_vlc_fullscreen = False

        # Binds
        self.bind("<Escape>", self._exit_fullscreen)
        self.bind("<space>", self._toggle_play_event)
        self.bind("<Left>", lambda e: self._seek(-5))
        self.bind("<Right>", lambda e: self._seek(5))
        self.bind("z", self._toggle_zoom)
        self.bind("Z", self._toggle_zoom)
        
        self._create_ui()
        self._load_video_moviepy(self.current_video_path)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if start_fullscreen:
            self.after(200, self._toggle_fullscreen)
        elif mode == "view":
            if self.use_vlc_always:
                self.after(300, self._switch_to_vlc)
            else:
                self.after(300, self._toggle_play)

    def _center_window_top(self):
        try:
            screen_width = self.winfo_screenwidth()
            x = int((screen_width / 2) - (self.width / 2))
            y = 10 
            self.geometry(f"{self.width}x{self.height}+{x}+{y}")
        except:
            self.geometry(f"{self.width}x{self.height}+100+10")

    def _load_video_moviepy(self, path):
        if hasattr(self, 'full_clip') and self.full_clip: self.full_clip.close()
        try:
            self.full_clip = VideoFileClip(path)
            self.duration = self.full_clip.duration
            self.end_time = self.duration
            self.slider.configure(to=self.duration)
            if self.mode == "trim": self.lbl_end.configure(text=f"End: {self.duration:.2f}s")
            self._update_preview(self.current_time)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load video: {e}")
            self.destroy()

    def _create_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self.video_container = ctk.CTkFrame(self, fg_color="black")
        self.video_container.grid(row=0, column=0, sticky="nsew")
        self.video_container.grid_rowconfigure(0, weight=1)
        self.video_container.grid_columnconfigure(0, weight=1)

        self.image_label = ctk.CTkLabel(self.video_container, text="", fg_color="black")
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.image_label.bind("<Button-1>", self._on_video_click)         
        self.image_label.bind("<Double-Button-1>", self._toggle_fullscreen) 

        self.vlc_frame = tk.Frame(self.video_container, bg="black")
        self.vlc_canvas = tk.Canvas(self.vlc_frame, bg="black", highlightthickness=0)
        self.vlc_canvas.pack(fill="both", expand=True)
        self.vlc_canvas.bind("<Button-1>", self._on_video_click)
        self.vlc_canvas.bind("<Double-Button-1>", self._exit_fullscreen) 

        self.controls_container = ctk.CTkFrame(self, fg_color="#2b2b2b")
        self.controls_container.grid(row=1, column=0, sticky="ew")
        self.controls_container.grid_columnconfigure(0, weight=1)

        playback_frame = ctk.CTkFrame(self.controls_container, fg_color="transparent")
        playback_frame.pack(fill="x", pady=(5, 0))
        playback_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(playback_frame, text="⏪ -5s", width=50, command=lambda: self._seek(-5)).grid(row=0, column=0, padx=5)
        self.play_btn = ctk.CTkButton(playback_frame, text="▶", width=50, command=self._toggle_play)
        self.play_btn.grid(row=0, column=1, padx=5)
        ctk.CTkButton(playback_frame, text="+5s ⏩", width=50, command=lambda: self._seek(5)).grid(row=0, column=2, padx=5)

        self.slider = ctk.CTkSlider(playback_frame, from_=0, to=100, command=self._on_slider_drag)
        self.slider.grid(row=0, column=3, padx=10, sticky="ew")
        self.slider.set(0)

        self.time_lbl = ctk.CTkLabel(playback_frame, text="00:00.00", width=70, font=("Consolas", 12))
        self.time_lbl.grid(row=0, column=4, padx=5)

        tools_frame = ctk.CTkFrame(self.controls_container, fg_color="transparent")
        tools_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(tools_frame, text="Vol:").pack(side="left", padx=(10, 2))
        ctk.CTkSlider(tools_frame, width=80).pack(side="left", padx=5)
        ctk.CTkLabel(tools_frame, text="Speed:").pack(side="left", padx=(15, 2))
        self.speed_menu = ctk.CTkOptionMenu(tools_frame, values=["0.5x", "1.0x", "1.5x", "2.0x"], width=70, command=self._change_speed)
        self.speed_menu.pack(side="left", padx=5)
        self.speed_menu.set("1.0x")
        ctk.CTkButton(tools_frame, text="⛶ Fullscreen", width=90, command=self._toggle_fullscreen, fg_color="#444").pack(side="right", padx=10)

        if self.mode in ["trim", "extract"]:
            action_frame = ctk.CTkFrame(self.controls_container, fg_color="transparent")
            action_frame.pack(fill="x", pady=5)
            if self.mode == "trim": self._setup_trim_ui(action_frame)
            elif self.mode == "extract": self._setup_extract_ui(action_frame)

    def _setup_trim_ui(self, parent):
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        row1.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkButton(row1, text="[ Set Start", command=self._set_start, width=80, fg_color="#D35400").grid(row=0, column=0, padx=5)
        self.lbl_start = ctk.CTkLabel(row1, text="Start: 0.00s")
        self.lbl_start.grid(row=0, column=1, sticky="w")
        ctk.CTkButton(row1, text="] Set End", command=self._set_end, width=80, fg_color="#D35400").grid(row=0, column=2, padx=5)
        self.lbl_end = ctk.CTkLabel(row1, text=f"End: {self.duration:.2f}s")
        self.lbl_end.grid(row=0, column=3, sticky="w")

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkButton(row2, text="✂ Crop Selection", command=self._perform_crop, fg_color="#2980B9", width=120).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="🗑️ Delete Selection", command=self._perform_delete, fg_color="#C0392B", width=120).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="📥 Insert Clip", command=self._perform_insert, fg_color="#8E44AD", width=100).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="✅ Save", command=self._finish_editing, fg_color="green", width=80).pack(side="right", padx=5)
        ctk.CTkButton(row2, text="↺ Reset", command=self._perform_reset, fg_color="gray", width=60).pack(side="right", padx=5)

    def _setup_extract_ui(self, parent):
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(pady=5)
        if self.defaults and self.defaults['folder']:
             ctk.CTkButton(btn_frame, text="⚡ Quick Save", command=self._quick_save_frame, fg_color="#2980B9").pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="💾 Save As...", command=self._save_frame_as, fg_color="purple").pack(side="left", padx=10)

    def _switch_to_vlc(self):
        self.is_playing = False 
        self.image_label.grid_remove()
        self.vlc_frame.grid(row=0, column=0, sticky="nsew")
        self.video_container.update()
        
        self.active_engine = "vlc"
        media = self.vlc_instance.media_new(self.current_video_path)
        self.vlc_player.set_media(media)
        
        h = self.vlc_canvas.winfo_id()
        if os.name == 'nt': self.vlc_player.set_hwnd(h)
        else: self.vlc_player.set_xwindow(h)
        
        self.vlc_player.play()
        self.after(50, lambda: self.vlc_player.set_time(int(self.current_time * 1000)))
        
        self.is_playing = True
        self.play_btn.configure(text="⏸")
        self._vlc_monitor_loop()

    def _switch_to_moviepy(self):
        if self.vlc_player:
            t_ms = self.vlc_player.get_time()
            if t_ms > 0: self.current_time = t_ms / 1000.0
            self.vlc_player.stop()
        self.vlc_frame.grid_remove()
        self.active_engine = "moviepy"
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.is_playing = False
        self.play_btn.configure(text="▶")
        self._update_preview(self.current_time)

    def _vlc_monitor_loop(self):
        if self.active_engine == "vlc" and self.is_playing:
            if self.vlc_player.get_state() == vlc.State.Ended:
                self.vlc_player.set_media(self.vlc_player.get_media())
                self.vlc_player.play()
            t_ms = self.vlc_player.get_time()
            if t_ms >= 0:
                t_sec = t_ms / 1000.0
                self.current_time = t_sec
                self.slider.set(t_sec)
                mins = int(t_sec // 60); secs = int(t_sec % 60); frac = int((t_sec - int(t_sec)) * 100)
                self.time_lbl.configure(text=f"{mins:02}:{secs:02}.{frac:02}")
            self.after(200, self._vlc_monitor_loop)

    def _toggle_play_event(self, event=None): self._toggle_play()
    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.play_btn.configure(text="⏸" if self.is_playing else "▶")
        if self.active_engine == "vlc":
            if self.is_playing:
                self.vlc_player.play(); self._vlc_monitor_loop()
                if self.is_fullscreen: self._schedule_auto_hide()
            else:
                self.vlc_player.pause()
                if self.hide_task: self.after_cancel(self.hide_task)
        else:
            if self.is_playing:
                self.last_frame_time = time.time(); self._play_loop_moviepy()

    def _seek(self, seconds):
        if self.active_engine == "vlc":
            self.vlc_player.set_time(self.vlc_player.get_time() + (seconds * 1000))
        else:
            self.current_time = max(0, min(self.current_time + seconds, self.duration))
            self.slider.set(self.current_time)
            self._update_preview(self.current_time)

    def _on_slider_drag(self, value):
        self.current_time = float(value)
        if self.active_engine == "vlc":
            self.vlc_player.set_time(int(self.current_time * 1000))
        else:
            self._update_preview(self.current_time)
            self.last_frame_time = time.time()

    def _play_loop_moviepy(self):
        if not self.is_playing or self.active_engine != "moviepy": return
        now = time.time()
        delta = now - self.last_frame_time
        self.last_frame_time = now
        self.current_time += (delta * self.playback_speed)
        if self.current_time >= self.duration: self.current_time = 0
        self.slider.set(self.current_time)
        self._update_preview(self.current_time)
        self.after(33, self._play_loop_moviepy)

    def _update_preview(self, t):
        if self.active_engine != "moviepy": return
        mins = int(t // 60); secs = int(t % 60); frac = int((t - int(t)) * 100)
        self.time_lbl.configure(text=f"{mins:02}:{secs:02}.{frac:02}")
        try:
            frame = self.full_clip.get_frame(t)
            img = Image.fromarray(frame).copy()
            img_w, img_h = img.size
            if self.is_fullscreen:
                win_w = self.winfo_screenwidth()
                win_h = self.winfo_screenheight()
                if self.controls_visible: win_h = win_h - 100 
            else:
                win_w = self.winfo_width()
                win_h = int(self.editor_height * self.scale_factor)
            if win_w < 50: win_w = 800
            if win_h < 50: win_h = 400
            ratio = min(win_w / img_w, win_h / img_h)
            if self.is_zoomed: ratio = max(win_w / img_w, win_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)
            resize_method = Image.NEAREST if self.is_playing else Image.LANCZOS
            img = img.resize((new_w, new_h), resize_method)
            if self.is_zoomed:
                left = (new_w - win_w) / 2
                top = (new_h - win_h) / 2
                img = img.crop((left, top, left + win_w, top + win_h))
                new_w, new_h = img.size
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(new_w, new_h))
            self.image_label.configure(image=ctk_img)
            self.image_label.image = ctk_img 
        except Exception: pass

    def _toggle_zoom(self, event=None):
        self.is_zoomed = not self.is_zoomed
        if self.active_engine == "moviepy": self._update_preview(self.current_time)

    def _toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.old_geometry = self.geometry()
            self.transient(None); self.grab_release(); self.withdraw()
            self.overrideredirect(True)
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
            self.deiconify(); self.focus_force(); self._set_controls_visibility(False)
            if self.use_vlc_fullscreen: self._switch_to_vlc()
            else: self.update_idletasks(); self._update_preview(self.current_time)
        else:
            if self.active_engine == "vlc" and not self.use_vlc_always:
                self._switch_to_moviepy()
            elif self.active_engine == "vlc" and self.use_vlc_always:
                pass

            self.withdraw(); self.overrideredirect(False); self.geometry(self.old_geometry)
            self.transient(self.parent_window); self.grab_set(); self.deiconify()
            self._set_controls_visibility(True)
            if self.active_engine == "moviepy":
                self.update_idletasks(); self._update_preview(self.current_time)

    def _change_speed(self, choice):
        self.playback_speed = float(choice.replace("x", ""))
        if self.active_engine == "vlc": self.vlc_player.set_rate(self.playback_speed)

    def _on_video_click(self, event):
        if self.is_fullscreen:
            self._set_controls_visibility(not self.controls_visible)
            if self.controls_visible and self.is_playing: self._schedule_auto_hide()
        else:
            self._toggle_play()

    def _set_controls_visibility(self, visible):
        self.controls_visible = visible
        if visible: self.controls_container.grid(); self.controls_container.lift()
        else: self.controls_container.grid_remove()

    def _schedule_auto_hide(self):
        if self.hide_task: self.after_cancel(self.hide_task)
        self.hide_task = self.after(3000, self._auto_hide_trigger)

    def _auto_hide_trigger(self):
        if self.is_fullscreen and self.is_playing: self._set_controls_visibility(False)

    def _exit_fullscreen(self, event=None):
        if self.is_fullscreen: self._toggle_fullscreen()

    def _get_temp_path(self, suffix): return os.path.abspath(f"TEMP_{int(time.time())}_{suffix}.mp4")

    def _update_current_video(self, new_path, is_reset=False):
        if self.active_engine == "vlc": self.vlc_player.stop()
        self.is_playing = False
        if not is_reset and new_path != self.original_video_path: self.temp_files.append(new_path)
        self.current_video_path = new_path
        self._load_video_moviepy(new_path)
        self.play_btn.configure(text="▶")
        self.slider.set(0); self.start_time = 0
        if hasattr(self, 'lbl_start'): self.lbl_start.configure(text="Start: 0.00s")
        
        if self.use_vlc_always:
            self._switch_to_vlc()

    def _perform_crop(self):
        if self.start_time >= self.end_time: return
        self.configure(cursor="watch"); self.update(); out = self._get_temp_path("crop")
        try:
            res = crop_video_backend(self.current_video_path, self.start_time, self.end_time, out)
            self._update_current_video(res)
        except Exception as e: messagebox.showerror("Error", str(e))
        self.configure(cursor="")

    def _perform_delete(self):
        self.configure(cursor="watch"); self.update(); out = self._get_temp_path("del")
        try:
            res = delete_section_backend(self.current_video_path, self.start_time, self.end_time, out)
            self._update_current_video(res)
        except Exception as e: messagebox.showerror("Error", str(e))
        self.configure(cursor="")

    def _perform_insert(self):
        path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi")]); 
        if not path: return
        self.configure(cursor="watch"); self.update(); out = self._get_temp_path("ins"); cur_t = self.slider.get()
        try:
            res = insert_clip_backend(self.current_video_path, path, cur_t, out)
            self._update_current_video(res)
        except Exception as e: messagebox.showerror("Error", str(e))
        self.configure(cursor="")

    def _perform_reset(self):
        if messagebox.askyesno("Reset", "Revert?"): self._update_current_video(self.original_video_path, is_reset=True)

    def _finish_editing(self):
        if self.callback: self.callback(self.current_video_path)
        self._on_close(destroy_temp=False)

    def _quick_save_frame(self):
        if not self.defaults or not self.defaults['folder']: return
        name = f"{self.defaults['name']}_frame_{int(time.time())}.jpg"
        path = os.path.join(self.defaults['folder'], name)
        if extract_frame_backend(self.current_video_path, self.current_time, path):
            messagebox.showinfo("Saved", f"Saved to:\n{name}")

    def _save_frame_as(self):
        output_path = filedialog.asksaveasfilename(defaultextension=".jpg", filetypes=[("JPEG", "*.jpg")])
        if output_path:
            if extract_frame_backend(self.current_video_path, self.current_time, output_path):
                messagebox.showinfo("Done", "Frame Saved!")

    def _set_start(self):
        self.start_time = self.slider.get()
        self.lbl_start.configure(text=f"Start: {self.start_time:.2f}s", text_color="orange")

    def _set_end(self):
        self.end_time = self.slider.get()
        self.lbl_end.configure(text=f"End: {self.end_time:.2f}s", text_color="orange")

    def _on_close(self, destroy_temp=True):
        self.is_playing = False
        if self.vlc_player: self.vlc_player.stop()
        if hasattr(self, 'full_clip') and self.full_clip: self.full_clip.close()
        if destroy_temp:
            for f in self.temp_files:
                try: os.remove(f)
                except: pass
        else:
            for f in self.temp_files:
                if f != self.current_video_path:
                    try: os.remove(f)
                    except: pass
        self.destroy()

# --- 4. Main GUI Application Class ---

class VideoCombinerApp(ctk.CTk, TkinterDnD.DnDWrapper):
    CONFIG_FILE = "video_combiner_config.json"

    def __init__(self):
        super().__init__()
        
        # --- DRAG AND DROP INIT ---
        if DND_AVAILABLE:
            self.TkdndVersion = TkinterDnD._require(self)
        
        self.title("🎬 Custom Video Combiner")
        
        self.width = 1200 
        self.height = 800
        self._center_window_top()
        
        # Data
        self.playlist_data = [] 
        self.selected_index = -1
        self.drag_source_idx = None
        self.newly_added_indices = set() # <--- ADD THIS LINE
        
        # Settings Defaults
        self.default_folder = ""
        self.default_name = "output_video"
        self.preview_fps = 10      
        self.preview_height = 250
        self.preview_duration = 3.0
        self.after_merge_action = "System Player"
        self.use_vlc_fullscreen = True
        self.editor_window_height = 600 
        self.gif_settings = {"fps": 10, "scale": 0.5, "speed": 1.0}
        self.ai_tools_dir = "" 
        
        self._load_settings_from_file()

        # Animation / Threading State
        self.current_anim_id = 0 
        self.preview_cache = []   
        self.preview_idx = 0
        self.preview_delay = 100
        self.preview_job = None
        self.preview_container = None 
        self.mini_preview_label = None 
        self.load_lock = threading.Lock()
        
        # Sidebar State
        self.sidebar_expanded = True
        self.sidebar_width = 180
        self.sidebar_min_width = 50
        
        self._create_layout_grid()
        self._create_sidebar()
        self._create_main_area()
        self._update_total_duration()
        
        self.bind("<Delete>", lambda e: self._remove_clip())
        self.bind("<BackSpace>", lambda e: self._remove_clip()) 
        
        # --- REGISTER DRAG AND DROP ---
        self._setup_dnd_events()

    def _setup_dnd_events(self):
        if not DND_AVAILABLE: return

        # Helper to register a widget and bind the events
        def register_widget(w):
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind('<<Drop>>', self._on_drop_files)
                w.dnd_bind('<<DragEnter>>', self._on_drag_enter)
                w.dnd_bind('<<DragLeave>>', self._on_drag_leave)
            except Exception as e:
                print(f"Could not register {w}: {e}")

        # 1. Register Main Window
        register_widget(self)

        # 2. Register Containers (The Blocking Layers)
        if hasattr(self, 'sidebar_frame'): register_widget(self.sidebar_frame)
        if hasattr(self, 'preview_container'): register_widget(self.preview_container)
        
        # 3. Register Scroll Frame (The Playlist)
        # Note: For CTkScrollableFrame, we must register the internal canvas
        if hasattr(self, 'scroll_frame'): register_widget(self.scroll_frame._parent_canvas)

        # 4. Register All Sidebar Buttons (Crucial!)
        if hasattr(self, 'sidebar_buttons'):
            for item in self.sidebar_buttons:
                register_widget(item["btn"])
            
        # 5. Register Header/Footer buttons if they are large enough to be annoying
        if hasattr(self, 'save_as_btn'): register_widget(self.save_as_btn)
        if hasattr(self, 'quick_save_btn'): register_widget(self.quick_save_btn)

    def _on_drag_enter(self, event):
        # Triggered when entering ANY registered widget
        try:
            # Visual Cue: Bright Green Sidebar
            if self.sidebar_frame._fg_color != "#2ECC71":
                self.sidebar_frame.configure(fg_color="#2ECC71")
                self.scroll_frame.configure(border_color="#2ECC71", border_width=4)
        except Exception: pass

    def _on_drag_leave(self, event):
        # Triggered when leaving a widget. 
        # CRITICAL: Only reset if we are actually leaving the APPLICATION WINDOW.
        try:
            x, y = self.winfo_pointerxy()
            root_x = self.winfo_rootx()
            root_y = self.winfo_rooty()
            width = self.winfo_width()
            height = self.winfo_height()

            # If mouse is still inside the App Window boundaries, DO NOTHING.
            # This prevents flickering when moving from Sidebar -> Button -> Main Window.
            if (root_x <= x <= root_x + width) and (root_y <= y <= root_y + height):
                return

            # Reset Visuals
            self.sidebar_frame.configure(fg_color="#212121")
            self.scroll_frame.configure(border_color="#2b2b2b", border_width=2)
        except Exception: pass

    def _on_drop_files(self, event):
            # Force visual reset immediately
            try:
                self.sidebar_frame.configure(fg_color="#212121")
                self.scroll_frame.configure(border_color="#2b2b2b", border_width=2)
            except: pass
        
            if not event.data: return
            raw_data = event.data
            
            # Parse dropped files (Handle {} for paths with spaces)
            files = []
            if '{' in raw_data:
                # Matches {Path With Spaces} or SimplePath
                pattern = re.compile(r'\{.*?\}|\S+')
                matches = pattern.findall(raw_data)
                for m in matches:
                    files.append(m.strip('{}'))
            else:
                files = raw_data.split()

            # Filter and Add
            valid_files = [f for f in files if os.path.exists(f) and f.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv'))]
            
            if valid_files:
                self.configure(cursor="watch"); self.update()
                for clip_path in valid_files:
                    try:
                        meta = extract_clip_metadata(clip_path)
                        self.playlist_data.append({
                            'path': clip_path, 
                            'thumb': meta['thumb'], 
                            'name': os.path.basename(clip_path), 
                            'duration': meta['duration'], 
                            'res': meta['resolution'], 
                            'fps': meta['fps'], 
                            'size_str': meta['size_str']
                        })
                    except Exception as e:
                        print(f"Error loading dropped file {clip_path}: {e}")
                
                self.configure(cursor="")
                self._update_total_duration()
                self._render_playlist()

    def _center_window_top(self):
        try:
            scale = ctypes.windll.user32.GetDpiForSystem() / 96.0 if hasattr(ctypes.windll.user32, 'GetDpiForSystem') else 1.0
            screen_width = self.winfo_screenwidth()
            x = int((screen_width / 2) - (self.width / 2))
            y = 10 
            self.geometry(f"{self.width}x{self.height}+{x}+{y}")
        except:
            self.geometry(f"{self.width}x{self.height}+100+10")

    def _create_layout_grid(self):
        self.grid_rowconfigure(0, weight=0) 
        self.grid_rowconfigure(1, weight=1) 
        self.grid_rowconfigure(2, weight=0) 
        self.grid_columnconfigure(0, weight=0) 
        self.grid_columnconfigure(1, weight=1) 
        self.grid_columnconfigure(2, weight=0) 

    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=self.sidebar_width, corner_radius=0, fg_color="#212121")
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar_frame.pack_propagate(False)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Video\nCombiner", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.pack(pady=(30, 20), padx=10)

        self.sidebar_buttons = [] 

        self._add_sidebar_btn("➕", "Add Clip", self._add_clip)
        self._add_sidebar_btn("➖", "Remove", self._remove_clip)
        self._add_separator()
        self._add_sidebar_btn("✂️", "Editor", self._open_trim_dialog, fg_color="#D35400", hover="#A04000")
        self._add_sidebar_btn("📷", "Extract", self._open_frame_extract_dialog, fg_color="#7D3C98", hover="#5B2C6F")
        self._add_sidebar_btn("📏", "Resize", self._open_resize_tool, fg_color="#1F618D", hover="#154360")
        self._add_sidebar_btn("🚀", "Upscale", self._open_upscale_tool, fg_color="#8E44AD", hover="#5B2C6F")
        self._add_sidebar_btn("💨", "Smooth / FPS", self._open_interpolation_tool, fg_color="#E67E22", hover="#D35400")
        self._add_sidebar_btn("🎬", "GIF Tool", self._open_gif_converter, fg_color="#2ECC71", hover="#27AE60")
        self._add_sidebar_btn("🔄", "Converter", self._open_converter_tool, fg_color="#16A085", hover="#117864")
        self._add_separator()
        self._add_sidebar_btn("⚙️", "Settings", self._open_settings_dialog, fg_color="#555555", hover="#333333")
        self._add_sidebar_btn("❌", "Clear All", self._clear_list, fg_color="#C0392B", hover="#922B21")
        
    def _add_sidebar_btn(self, icon, text, command, fg_color="transparent", hover=None):
            full_text = f"{icon} {text}"
            btn = ctk.CTkButton(self.sidebar_frame, text=full_text, command=command, fg_color=fg_color, anchor="w", height=40, font=("Arial", 13, "bold"))
            if hover: btn.configure(hover_color=hover)
            else: btn.configure(hover_color="#444")
            btn.pack(fill="x", padx=10, pady=5)
            self.sidebar_buttons.append({"btn": btn, "icon": icon, "full_text": full_text})

    def _add_separator(self):
        line = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color="#444")
        line.pack(fill="x", padx=10, pady=10)

    def _toggle_sidebar(self):
        if self.sidebar_expanded:
            for item in self.sidebar_buttons:
                item["btn"].configure(text=item["icon"].strip(), anchor="center")
                item["btn"].pack_configure(padx=0)
                item["btn"].configure(width=self.sidebar_min_width)
            self.logo_label.configure(text="V\nC") 
            self._animate_sidebar(self.sidebar_width, self.sidebar_min_width)
            self.sidebar_expanded = False
        else:
            for item in self.sidebar_buttons:
                item["btn"].configure(text=item["full_text"], anchor="w")
                item["btn"].pack_configure(padx=10)
                item["btn"].configure(width=self.sidebar_width - 20)
            self.logo_label.configure(text="Video\nCombiner") 
            self._animate_sidebar(self.sidebar_min_width, self.sidebar_width)
            self.sidebar_expanded = True
            
    def _animate_sidebar(self, start_w, end_w):
            if start_w < end_w: new_w = min(start_w + 15, end_w) 
            else: new_w = max(start_w - 15, end_w)
            self.sidebar_frame.configure(width=new_w)
            if new_w != end_w: self.after(10, lambda: self._animate_sidebar(new_w, end_w))

    def _create_main_area(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.grid(row=0, column=1, columnspan=2, sticky="ew", padx=10, pady=(10,0))
        self.menu_btn = ctk.CTkButton(header_frame, text="☰", width=40, height=40, command=self._toggle_sidebar, fg_color="transparent", hover_color="#333", font=("Arial", 20))
        self.menu_btn.pack(side="left")
        ctk.CTkLabel(header_frame, text="Playlist Workspace", font=("Arial", 16, "bold"), text_color="#888").pack(side="left", padx=10)

        # IMPORTANT: Initialize with border_width=2 so the layout doesn't jump
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Clips (Drag to Reorder)", border_width=2, border_color="#2b2b2b")
        self.scroll_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        self.scroll_frame._parent_canvas.bind("<Button-1>", lambda e: self._flash_border(self.scroll_frame, "#1F6AA5"))
        def on_bg_dbl_click(event):
            self._flash_border(self.scroll_frame, "red")
            self._add_clip()
        self.scroll_frame._parent_canvas.bind("<Double-Button-1>", on_bg_dbl_click)

        sidebar_right = ctk.CTkFrame(self, width=320)
        sidebar_right.grid(row=1, column=2, padx=(0, 10), pady=10, sticky="ns")
        sidebar_right.grid_columnconfigure(0, weight=1)

        self.preview_container = ctk.CTkFrame(sidebar_right, fg_color="#1a1a1a", height=300, width=300, corner_radius=5, border_width=2, border_color="#2b2b2b")
        self.preview_container.grid(row=0, column=0, padx=10, pady=(15, 10))
        self.preview_container.pack_propagate(False) 
        self.preview_container.bind("<Button-1>", lambda e: self._flash_border(self.preview_container, "#1F6AA5"))
        self.preview_container.bind("<Double-Button-1>", lambda e: self._flash_border(self.preview_container, "red"))
        
        self._recreate_preview_label(text="[No Clip Selected]")

        self.info_frame = ctk.CTkFrame(sidebar_right, fg_color="transparent")
        self.info_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.lbl_info_name = ctk.CTkLabel(self.info_frame, text="---", text_color="#aaa", font=("Arial", 11))
        self.lbl_info_name.pack(fill="x")
        details_grid = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        details_grid.pack(fill="x", pady=2)
        self.lbl_info_size = ctk.CTkLabel(details_grid, text="Size: --", font=("Arial", 11))
        self.lbl_info_size.pack(side="left", padx=5)
        self.lbl_info_res = ctk.CTkLabel(details_grid, text="Res: --", font=("Arial", 11))
        self.lbl_info_res.pack(side="right", padx=5)
        self.lbl_info_dur = ctk.CTkLabel(self.info_frame, text="Duration: --", font=("Arial", 11))
        self.lbl_info_dur.pack(fill="x")
        self.duration_label = ctk.CTkLabel(sidebar_right, text="Total: 00:00:00", font=ctk.CTkFont(size=14, weight="bold"))
        self.duration_label.grid(row=2, column=0, padx=10, pady=(20, 5))
        order_frame = ctk.CTkFrame(sidebar_right, fg_color="transparent")
        order_frame.grid(row=3, column=0, pady=10)
        ctk.CTkButton(order_frame, text="▲ Up", width=80, command=lambda: self._move_clip(-1)).pack(side="left", padx=5)
        ctk.CTkButton(order_frame, text="▼ Down", width=80, command=lambda: self._move_clip(1)).pack(side="left", padx=5)
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=2, column=1, columnspan=2, padx=10, pady=10, sticky="ew")
        footer_frame.grid_columnconfigure((0, 1), weight=1)
        self.progress_bar = ctk.CTkProgressBar(footer_frame)
        self.progress_bar.grid(row=0, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        btn_container = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_container.grid(row=1, column=0, columnspan=2)
        self.quick_save_btn = ctk.CTkButton(btn_container, text="⚡ Quick Combine", command=self._quick_combine, fg_color="#2980B9", state="disabled", width=180, height=40)
        self.quick_save_btn.pack(side="left", padx=10)
        self.save_as_btn = ctk.CTkButton(btn_container, text="💾 Save As...", command=self._combine_save_as, fg_color="green", hover_color="#006400", width=180, height=40)
        self.save_as_btn.pack(side="left", padx=10)
        
    def _force_background_bindings(self):
        try:
            canvas = self.scroll_frame._parent_canvas
            canvas.unbind("<Button-1>")
            canvas.unbind("<Double-Button-1>")
            canvas.bind("<Button-1>", lambda e: self._flash_border(self.scroll_frame, "#1F6AA5"))
            def on_bg_dbl_click(event):
                self._flash_border(self.scroll_frame, "red")
                self._add_clip()
            canvas.bind("<Double-Button-1>", on_bg_dbl_click)
        except Exception: pass
        
    def _flash_border(self, widget, color, duration=1000):
        try:
            reset_color = "#2b2b2b"
            if hasattr(widget, "_fg_color"): reset_color = widget._fg_color
            if reset_color == "transparent" or reset_color is None: reset_color = "#2b2b2b"
            if widget.winfo_exists(): widget.configure(border_color=color)
            if hasattr(widget, "flash_job") and widget.flash_job:
                try: self.after_cancel(widget.flash_job)
                except: pass
            def reset_step():
                try:
                    if widget.winfo_exists(): widget.configure(border_color=reset_color)
                except Exception: pass
            widget.flash_job = self.after(duration, reset_step)
        except Exception: pass
    
    def _load_settings_from_file(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.default_folder = data.get("default_folder", "")
                    self.default_name = data.get("default_name", "output_video")
                    self.preview_fps = data.get("preview_fps", 10)
                    self.preview_height = data.get("preview_height", 250)
                    self.preview_duration = data.get("preview_duration", 3.0)
                    self.after_merge_action = data.get("after_merge_action", "System Player")
                    self.use_vlc_fullscreen = data.get("use_vlc_fullscreen", True)
                    self.editor_window_height = data.get("editor_window_height", 600)
                    if "gif_settings" in data: self.gif_settings = data["gif_settings"]
                    self.ai_tools_dir = data.get("ai_tools_dir", "")
            except Exception: pass

    def _save_settings_to_file(self):
        data = {
            "default_folder": self.default_folder,
            "default_name": self.default_name,
            "preview_fps": self.preview_fps,
            "preview_height": self.preview_height,
            "preview_duration": self.preview_duration,
            "after_merge_action": self.after_merge_action,
            "use_vlc_fullscreen": self.use_vlc_fullscreen,
            "editor_window_height": self.editor_window_height,
            "gif_settings": self.gif_settings,
            "ai_tools_dir": self.ai_tools_dir
        }
        try:
            with open(self.CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)
        except Exception: pass

    def _recreate_preview_label(self, text="", image=None):
        if self.mini_preview_label:
            try: self.mini_preview_label.destroy()
            except: pass
            self.mini_preview_label = None
        self.mini_preview_label = ctk.CTkLabel(self.preview_container, text=text, image=image)
        self.mini_preview_label.pack(expand=True, fill="both", padx=3, pady=3)
        if image: self.mini_preview_label.image = image
        self.mini_preview_label.bind("<Button-1>", lambda e: self._flash_border(self.preview_container, "#1F6AA5"))
        def on_dbl(event):
            self._flash_border(self.preview_container, "red")
            self._on_mini_preview_dbl_click(event)
        self.mini_preview_label.bind("<Double-Button-1>", on_dbl)

    def _on_mini_preview_dbl_click(self, event):
        if 0 <= self.selected_index < len(self.playlist_data):
            self._pause_mini_preview() # <--- PAUSE
            
            path = self.playlist_data[self.selected_index]['path']
            popup = VideoEditorPopup(self, path, mode="view", start_fullscreen=True, 
                                     use_vlc=self.use_vlc_fullscreen, 
                                     editor_height=self.editor_window_height)
            
            self.wait_window(popup)    # <--- WAIT
            self._resume_mini_preview() # <--- RESUME

    def _open_resize_tool(self):
            if not self.playlist_data:
                messagebox.showwarning("Warning", "Playlist is empty.")
                return
            
            self._pause_mini_preview()
            
            dialog = ctk.CTkToplevel(self)
            dialog.title("Resize / Crop Video")
            dialog.geometry("400x450") # Increased height
            dialog.transient(self)
            dialog.grab_set()
            
            ctk.CTkLabel(dialog, text="Resize Settings", font=("Arial", 18, "bold")).pack(pady=10)

            # --- Resolution Section ---
            frame_res = ctk.CTkFrame(dialog, fg_color="transparent")
            frame_res.pack(fill="x", padx=20, pady=5)
            
            ctk.CTkLabel(frame_res, text="Target Size:", width=80, anchor="w").pack(side="left")
            self.resize_var = ctk.StringVar(value="Match Clip #1")
            
            def on_preset_change(choice):
                if choice == "Custom":
                    entry_w.configure(state="normal"); entry_h.configure(state="normal")
                else:
                    entry_w.configure(state="disabled"); entry_h.configure(state="disabled")
                    
            combo = ctk.CTkOptionMenu(frame_res, variable=self.resize_var, values=["Match Clip #1", "1920x1080 (1080p)", "1280x720 (720p)", "Custom"], command=on_preset_change)
            combo.pack(side="left", padx=10, fill="x", expand=True)
            
            frame_custom = ctk.CTkFrame(dialog, fg_color="transparent")
            frame_custom.pack(fill="x", padx=20, pady=5)
            entry_w = ctk.CTkEntry(frame_custom, width=70, placeholder_text="Width")
            entry_w.pack(side="left", padx=(90, 5))
            ctk.CTkLabel(frame_custom, text="x").pack(side="left")
            entry_h = ctk.CTkEntry(frame_custom, width=70, placeholder_text="Height")
            entry_h.pack(side="left", padx=5)
            entry_w.configure(state="disabled"); entry_h.configure(state="disabled")

            # --- Mode Section (NEW) ---
            frame_mode = ctk.CTkFrame(dialog, fg_color="transparent")
            frame_mode.pack(fill="x", padx=20, pady=10)
            
            ctk.CTkLabel(frame_mode, text="Resize Mode:", width=80, anchor="w").pack(side="left")
            mode_var = ctk.StringVar(value="Fit (Black Bars)")
            mode_menu = ctk.CTkOptionMenu(frame_mode, variable=mode_var, values=["Stretch (Distort)", "Fit (Black Bars)", "Crop to Fill"])
            mode_menu.pack(side="left", padx=10, fill="x", expand=True)

            # --- Anchor Section (NEW - Only shows for Crop) ---
            frame_anchor = ctk.CTkFrame(dialog, fg_color="transparent")
            frame_anchor.pack(fill="x", padx=20, pady=5)
            
            ctk.CTkLabel(frame_anchor, text="Crop Anchor:", width=80, anchor="w").pack(side="left")
            anchor_var = ctk.StringVar(value="Center")
            anchor_menu = ctk.CTkOptionMenu(frame_anchor, variable=anchor_var, values=["Center", "Top-Left", "Bottom-Right"], state="disabled")
            anchor_menu.pack(side="left", padx=10, fill="x", expand=True)

            def on_mode_change(choice):
                if choice == "Crop to Fill":
                    anchor_menu.configure(state="normal")
                else:
                    anchor_menu.configure(state="disabled")
            
            mode_menu.configure(command=on_mode_change)
            on_mode_change("Fit (Black Bars)") # Init state

            # --- Scope Section ---
            frame_scope = ctk.CTkFrame(dialog, fg_color="transparent")
            frame_scope.pack(fill="x", padx=20, pady=10)
            scope_var = ctk.StringVar(value="All Clips")
            if self.selected_index >= 0: ctk.CTkRadioButton(frame_scope, text="Selected Clip Only", variable=scope_var, value="Selected").pack(anchor="w", pady=5)
            ctk.CTkRadioButton(frame_scope, text="All Clips in Playlist", variable=scope_var, value="All Clips").pack(anchor="w", pady=5)

            def run_resize():
                # 1. Get Width/Height
                mode_str = self.resize_var.get()
                target_w, target_h = 0, 0
                if mode_str == "Match Clip #1":
                    if not self.playlist_data: return
                    target_w, target_h = self.playlist_data[0]['res']
                elif "1080p" in mode_str: target_w, target_h = 1920, 1080
                elif "720p" in mode_str: target_w, target_h = 1280, 720
                elif mode_str == "Custom":
                    try: target_w = int(entry_w.get()); target_h = int(entry_h.get())
                    except: messagebox.showerror("Error", "Invalid Resolution"); return
                
                if target_w <= 0 or target_h <= 0: return

                # 2. Get Mode/Anchor
                m_val = mode_var.get()
                mode = "stretch"
                if "Fit" in m_val: mode = "fit"
                elif "Crop" in m_val: mode = "crop"
                
                a_val = anchor_var.get().lower().replace(" ", "-") # "Top-Left" -> "top-left"
                
                # 3. Get Scope
                indices = []
                if scope_var.get() == "Selected" and self.selected_index >= 0: indices = [self.selected_index]
                else: indices = list(range(len(self.playlist_data)))
                
                if not indices: return
                
                if not messagebox.askyesno("Confirm", f"Resize {len(indices)} clip(s)?\nTarget: {target_w}x{target_h}\nMode: {m_val}"): return
                
                dialog.destroy()
                # Pass new args to thread starter
                self._start_resize_thread(indices, target_w, target_h, mode, a_val)

            ctk.CTkButton(dialog, text="Apply Resize", command=run_resize, fg_color="#1F618D").pack(pady=20)
            
            self.wait_window(dialog)
            self._resume_mini_preview()

        # --- Update Thread Starter to accept extra args ---
    def _start_resize_thread(self, indices, w, h, mode, anchor):
            self.progress_bar.set(0)
            self.save_as_btn.configure(text="Resizing...", state="disabled")
            self.quick_save_btn.configure(state="disabled")
            threading.Thread(target=self._resize_worker, args=(indices, w, h, mode, anchor), daemon=True).start()

        # --- Update Worker to pass args to backend ---
    def _resize_worker(self, indices, w, h, mode, anchor):
            total = len(indices)
            success_count = 0
            for step, idx in enumerate(indices):
                item = self.playlist_data[idx]
                
                # Skip only if exact same res AND mode is stretch (since other modes might change aspect ratio)
                if item['res'] == (w, h) and mode == "stretch": 
                    success_count += 1; continue
                    
                name_no_ext = os.path.splitext(item['name'])[0]
                new_name = f"RESIZED_{mode}_{w}x{h}_{name_no_ext}.mp4"
                out_path = os.path.abspath(new_name)
                
                self.after(0, lambda p=(step/total): self.progress_bar.set(p))
                
                try:
                    # CALL BACKEND WITH NEW ARGS
                    resize_clip_backend(item['path'], w, h, out_path, mode=mode, anchor=anchor)
                    
                    new_meta = extract_clip_metadata(out_path)
                    self.playlist_data[idx] = {'path': out_path, 'thumb': new_meta['thumb'], 'name': new_name, 'duration': new_meta['duration'], 'res': new_meta['resolution'], 'fps': new_meta['fps'], 'size_str': new_meta['size_str']}
                    success_count += 1
                except Exception as e:
                    print(f"Resize failed: {e}")
                    
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, self._on_resize_complete)

    def _on_resize_complete(self):
        self._render_playlist() 
        self.save_as_btn.configure(text="💾 Combine & Save As...", state="normal")
        if self.default_folder: self.quick_save_btn.configure(state="normal")
        if self.selected_index == -1 and self.playlist_data: self._select_item(0)
        elif self.selected_index >= 0: self._select_item(self.selected_index)
        messagebox.showinfo("Done", "Resolution resizing complete!")

    def _open_upscale_tool(self):
        self._pause_mini_preview()
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("🚀 High-Quality Upscaler")
        dialog.geometry("500x620") 
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Upscale Video & Images", font=("Arial", 18, "bold")).pack(pady=15)

        # 1. Input Selection
        input_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=5)
        
        self.upscale_path = ctk.StringVar()
        if self.selected_index >= 0:
            self.upscale_path.set(self.playlist_data[self.selected_index]['path'])
            
        entry_path = ctk.CTkEntry(input_frame, textvariable=self.upscale_path, placeholder_text="Select file...")
        entry_path.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def browse_upscale_file():
            f = filedialog.askopenfilename(filetypes=[("Media", "*.mp4 *.mov *.avi *.jpg *.png *.bmp")])
            if f: self.upscale_path.set(f)
            
        ctk.CTkButton(input_frame, text="Browse", width=60, command=browse_upscale_file).pack(side="right")

        # 2. Engine Selection
        engine_frame = ctk.CTkFrame(dialog, border_width=1, border_color="#444")
        engine_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(engine_frame, text="Upscale Engine:", font=("Arial", 12, "bold")).pack(pady=(10, 5))
        
        self.engine_var = ctk.StringVar(value="FFmpeg")
        self.face_enhance_var = ctk.BooleanVar(value=False)

        # --- MOVED: Define callbacks and widgets BEFORE waiting ---
        
        def on_engine_change():
            if self.engine_var.get() == "AI (Real-ESRGAN)":
                self.algo_menu.configure(state="disabled")
                self.sharpen_switch.configure(state="disabled")
                self.face_chk.configure(state="normal", text="Enhance Faces (Requires 'run_codeformer.bat')")
                self.vram_menu.configure(state="normal")
                status_lbl.configure(text="ℹ️ AI Mode active.", text_color="#3498DB")
            else:
                self.algo_menu.configure(state="normal")
                self.sharpen_switch.configure(state="normal")
                self.face_chk.configure(state="disabled", text="Enhance Faces (AI Only)")
                self.vram_menu.configure(state="disabled")
                status_lbl.configure(text="")

        r1 = ctk.CTkRadioButton(engine_frame, text="Standard (FFmpeg) - Fast, Good for minor resizing", variable=self.engine_var, value="FFmpeg", command=on_engine_change)
        r1.pack(anchor="w", padx=20, pady=5)
        
        r2 = ctk.CTkRadioButton(engine_frame, text="AI (Real-ESRGAN) - Slow, Best Quality (Detail creation)", variable=self.engine_var, value="AI (Real-ESRGAN)", command=on_engine_change)
        r2.pack(anchor="w", padx=20, pady=(5, 15))
        
        self.face_chk = ctk.CTkCheckBox(engine_frame, text="Enhance Faces (AI Only)", variable=self.face_enhance_var, state="disabled")
        self.face_chk.pack(anchor="w", padx=40, pady=5)

        # 3. Settings Grid
        grid_frame = ctk.CTkFrame(dialog)
        grid_frame.pack(fill="x", padx=20, pady=10)
        
        # Row 0: Factor & VRAM
        ctk.CTkLabel(grid_frame, text="Scale Factor:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.scale_mode = ctk.CTkOptionMenu(grid_frame, values=["2x", "4x"])
        self.scale_mode.grid(row=0, column=1, padx=10, pady=10, sticky="e")
        
        ctk.CTkLabel(grid_frame, text="VRAM (Tile Size):").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.vram_menu = ctk.CTkOptionMenu(grid_frame, values=["Auto (Recommended)", "Low (64)", "Medium (200)", "High (400)", "Ultra (512)"])
        self.vram_menu.grid(row=1, column=1, padx=10, pady=10, sticky="e")
        self.vram_menu.configure(state="disabled")

        # Row 1: Algo (FFmpeg only)
        ctk.CTkLabel(grid_frame, text="Algo (FFmpeg):").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.algo_menu = ctk.CTkOptionMenu(grid_frame, values=["Lanczos (Sharp)", "Spline (Smooth)", "Neighbor"])
        self.algo_menu.grid(row=2, column=1, padx=10, pady=10, sticky="e")
        
        # Sharpen
        self.sharpen_var = ctk.BooleanVar(value=True)
        self.sharpen_switch = ctk.CTkSwitch(dialog, text="Apply Smart Sharpening (FFmpeg)", variable=self.sharpen_var)
        self.sharpen_switch.pack(pady=5)
        
        status_lbl = ctk.CTkLabel(dialog, text="", text_color="orange")
        status_lbl.pack(pady=5)

        def run_upscale():
            src = self.upscale_path.get()
            if not os.path.exists(src):
                status_lbl.configure(text="Invalid file path.")
                return
            
            mode = self.engine_var.get()
            scale_str = self.scale_mode.get()
            factor = 4 if "4x" in scale_str else 2
            
            # Parse VRAM
            vram_choice = self.vram_menu.get()
            tile_size = 0
            if "Low" in vram_choice: tile_size = 64
            elif "Medium" in vram_choice: tile_size = 200
            elif "High" in vram_choice: tile_size = 400
            elif "Ultra" in vram_choice: tile_size = 512
            
            name, ext = os.path.splitext(os.path.basename(src))
            suffix = "_AI_x" + str(factor) if "AI" in mode else f"_Upscale_x{factor}"
            new_name = f"{name}{suffix}{ext}"
            
            save_path = filedialog.asksaveasfilename(initialfile=new_name, defaultextension=ext)
            if not save_path: return
            
            dialog.destroy()
            self._start_upscale_thread_v2(src, save_path, factor, mode, self.algo_menu.get(), self.sharpen_var.get(), tile_size)

        ctk.CTkButton(dialog, text="Start Processing", command=run_upscale, fg_color="#8E44AD", height=40).pack(fill="x", padx=20, pady=20)

        # --- FIX: WAIT COMMANDS ARE NOW AT THE VERY BOTTOM ---
        self.wait_window(dialog)
        self._resume_mini_preview()

    def _start_upscale_thread_v2(self, src, dest, factor, mode, algo_name, sharpen, tile_size):
        self.save_as_btn.configure(state="disabled")
        self.quick_save_btn.configure(state="disabled")
        
        # 1. Indeterminate Animation (Pulsing)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        
        # 2. Start Timer
        self._start_processing_timer("Upscaling")
        
        threading.Thread(target=self._upscale_worker_v2, args=(src, dest, factor, mode, algo_name, sharpen, tile_size), daemon=True).start()

    def _upscale_worker_v2(self, src, dest, factor, mode, algo_name, sharpen, tile_size):
        try:
            if "AI" in mode:
                # For AI, we can map the logger to determinate progress if available
                # But typically AI init takes time, so we switch modes
                def ai_logger(pct):
                    # Switch to determinate once we have real progress
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.set(pct))

                success, msg = upscale_with_ai_backend(src, dest, factor, ai_logger, exe_dir=self.ai_tools_dir, tile_size=tile_size)
                if not success: raise Exception(msg)
            else:
                # FFmpeg Backend
                algo_map = {"Lanczos (Sharp)": "lanczos", "Spline (Smooth)": "spline", "Neighbor": "neighbor"}
                upscale_media_backend(src, dest, factor, None, None, algo_map.get(algo_name, "lanczos"), sharpen)
            
            self.after(0, lambda: self._on_upscale_success_ui(dest))
                
        except Exception as e:
            err_msg = str(e)
            if "Executable not found" in err_msg:
                self.after(0, lambda: messagebox.showwarning("AI Engine Missing", "Please check AI Tools settings."))
            else:
                self.after(0, lambda: messagebox.showerror("Error", err_msg))
        
        # 3. Stop Timer and Reset UI
        self.is_processing = False 
        self.after(0, self._on_upscale_finished)

    def _on_upscale_success_ui(self, dest_path):
        # 1. Automatically load into playlist and mark as Green (from previous step)
        self._add_clip_from_path(dest_path, mark_new=True)

        # 2. Ask to preview
        if messagebox.askyesno("Complete", f"Processing Complete!\n\nFile added to playlist:\n{os.path.basename(dest_path)}\n\nPreview immediately?"):
            ext = os.path.splitext(dest_path)[1].lower()
            if ext in ['.jpg', '.png', '.bmp']:
                self._open_file_system(dest_path)
            else:
                self._pause_mini_preview() # <--- PAUSE
                
                popup = VideoEditorPopup(self, dest_path, mode="view", start_fullscreen=True, 
                                         use_vlc=self.use_vlc_fullscreen, 
                                         editor_height=self.editor_window_height)
                
                self.wait_window(popup)    # <--- WAIT
                self._resume_mini_preview() # <--- RESUME

    def _on_upscale_finished(self):
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.save_as_btn.configure(text="💾 Combine & Save As...", state="normal")
        if self.default_folder: self.quick_save_btn.configure(state="normal")

    def _open_interpolation_tool(self):
        self._pause_mini_preview() # <--- PAUSE
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("💨 Frame Interpolation (Smoother)")
        dialog.geometry("500x480") # Increased height slightly
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Increase Video Framerate", font=("Arial", 18, "bold")).pack(pady=15)

        # 1. File Selection
        input_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=5)
        
        self.interp_path = ctk.StringVar()
        if self.selected_index >= 0:
            self.interp_path.set(self.playlist_data[self.selected_index]['path'])
            
        entry_path = ctk.CTkEntry(input_frame, textvariable=self.interp_path, placeholder_text="Select video...")
        entry_path.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def browse_file():
            f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
            if f: self.interp_path.set(f)
            
        ctk.CTkButton(input_frame, text="Browse", width=60, command=browse_file).pack(side="right")

        # 2. Engine Selection
        engine_frame = ctk.CTkFrame(dialog, border_width=1, border_color="#444")
        engine_frame.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(engine_frame, text="Interpolation Engine:", font=("Arial", 12, "bold")).pack(pady=(10, 5))
        
        self.interp_engine_var = ctk.StringVar(value="FFmpeg")

        def on_engine_change():
            mode = self.interp_engine_var.get()
            if mode == "AI (RIFE)":
                setting_lbl.configure(text="Multiplier (RIFE):")
                # Updated values to include 4x
                setting_menu.configure(values=["2x (Double FPS)", "4x (Quadruple FPS)"], state="normal") 
                setting_menu.set("2x (Double FPS)")
                desc_lbl.configure(text="ℹ️ AI Mode: Requires 'rife-ncnn-vulkan'.\n4x is useful for low FPS (e.g., 16fps -> 64fps).", text_color="#3498DB")
            else:
                setting_lbl.configure(text="Target FPS:")
                setting_menu.configure(values=["60", "90", "120", "144"], state="normal")
                setting_menu.set("60")
                desc_lbl.configure(text="ℹ️ FFmpeg Mode: High CPU usage. Slow but reliable.", text_color="#aaa")

        r1 = ctk.CTkRadioButton(engine_frame, text="Standard (FFmpeg) - Configurable FPS", variable=self.interp_engine_var, value="FFmpeg", command=on_engine_change)
        r1.pack(anchor="w", padx=20, pady=5)
        
        r2 = ctk.CTkRadioButton(engine_frame, text="AI (RIFE) - Smoother Motion (GPU)", variable=self.interp_engine_var, value="AI (RIFE)", command=on_engine_change)
        r2.pack(anchor="w", padx=20, pady=(5, 15))

        # 3. Settings
        settings_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        settings_frame.pack(fill="x", padx=20, pady=10)
        
        setting_lbl = ctk.CTkLabel(settings_frame, text="Target FPS:", width=100, anchor="w")
        setting_lbl.pack(side="left")
        
        setting_menu = ctk.CTkOptionMenu(settings_frame, values=["60", "90", "120", "144"])
        setting_menu.pack(side="right", fill="x", expand=True)
        setting_menu.set("60")

        desc_lbl = ctk.CTkLabel(dialog, text="ℹ️ FFmpeg Mode: High CPU usage. Slow but reliable.", text_color="#aaa", font=("Arial", 11))
        desc_lbl.pack(pady=5)

        def run_interp():
            src = self.interp_path.get()
            if not os.path.exists(src): return
            
            mode = "rife" if "AI" in self.interp_engine_var.get() else "ffmpeg"
            val = setting_menu.get()
            
            target_fps = 60
            multiplier = 2
            
            if mode == "ffmpeg":
                target_fps = int(val)
            else:
                # Parse "2x..." or "4x..."
                if "4x" in val: multiplier = 4
                else: multiplier = 2
            
            # Generate output name
            name, ext = os.path.splitext(os.path.basename(src))
            if mode == "rife":
                suffix = f"_RIFE_{multiplier}x"
            else:
                suffix = f"_{target_fps}fps"
                
            new_name = f"{name}{suffix}{ext}"
            
            save_path = filedialog.asksaveasfilename(initialfile=new_name, defaultextension=ext)
            if not save_path: return
            
            dialog.destroy()
            self._start_interpolation_thread(src, save_path, mode, target_fps, multiplier)

        ctk.CTkButton(dialog, text="Start Interpolation", command=run_interp, fg_color="#E67E22", hover_color="#D35400", height=40).pack(fill="x", padx=20, pady=20)
        
        self.wait_window(dialog)    # <--- WAIT
        self._resume_mini_preview() # <--- RESUME

    def _start_interpolation_thread(self, src, dest, mode, fps, multiplier):
        self.save_as_btn.configure(state="disabled")
        self.quick_save_btn.configure(state="disabled")
        
        # 1. Indeterminate Animation
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        
        # 2. Start Timer
        self._start_processing_timer("Interpolating")
        
        threading.Thread(target=self._interpolation_worker, args=(src, dest, mode, fps, multiplier), daemon=True).start()

    def _interpolation_worker(self, src, dest, mode, fps, multiplier):
        def logger(pct):
            # Switch to determinate once progress starts
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.set(pct))

        try:
            success, msg = interpolate_video_backend(src, dest, method=mode, target_fps=fps, multiplier=multiplier, logger=logger, exe_dir=self.ai_tools_dir)
            
            if success:
                self.after(0, lambda: self._on_upscale_success_ui(dest)) 
            else:
                self.after(0, lambda: messagebox.showerror("Error", msg))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            
        # 3. Stop Timer and Reset
        self.is_processing = False
        self.after(0, self._on_upscale_finished)
        
    def _open_converter_tool(self):
        self._pause_mini_preview()
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Universal Converter (Batch)")
        dialog.geometry("550x600") # Increased height for new option
        dialog.transient(self)
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text="Batch Format Converter", font=("Arial", 18, "bold")).pack(pady=(15, 5))

        # --- File List Area ---
        list_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.convert_files = [] 
        if self.selected_index >= 0:
            self.convert_files.append(self.playlist_data[self.selected_index]['path'])

        self.file_list_box = ctk.CTkTextbox(list_frame, height=150)
        self.file_list_box.pack(fill="both", expand=True, pady=5)
        
        def update_file_display():
            self.file_list_box.configure(state="normal")
            self.file_list_box.delete("0.0", "end")
            text = "\n".join([os.path.basename(f) for f in self.convert_files])
            self.file_list_box.insert("0.0", text)
            self.file_list_box.configure(state="disabled")
            if self.convert_files: update_options(self.convert_files[0])
            status_lbl.configure(text=f"{len(self.convert_files)} file(s) selected")

        btn_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=5)
        
        def add_files():
            files = filedialog.askopenfilenames()
            if files:
                for f in files:
                    if f not in self.convert_files: self.convert_files.append(f)
                update_file_display()

        def clear_files():
            self.convert_files.clear(); update_file_display()

        ctk.CTkButton(btn_frame, text="➕ Add Files", command=add_files, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="🗑️ Clear List", command=clear_files, width=100, fg_color="#C0392B", hover_color="#922B21").pack(side="left", padx=5)
        status_lbl = ctk.CTkLabel(btn_frame, text="0 file(s) selected", text_color="gray")
        status_lbl.pack(side="right", padx=10)

        # --- Settings Area ---
        set_frame = ctk.CTkFrame(dialog)
        set_frame.pack(fill="x", padx=20, pady=15)
        
        vid_formats = ["MP4", "MKV", "AVI", "MOV", "WEBM", "MP3 (Audio)", "GIF"]
        img_formats = ["JPG", "PNG", "WEBP", "BMP", "ICO", "TIFF"]

        # Row 0: Format
        ctk.CTkLabel(set_frame, text="Target Format:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        format_menu = ctk.CTkOptionMenu(set_frame, values=vid_formats)
        format_menu.grid(row=0, column=1, padx=10, pady=10, sticky="e")
        
        # Row 1: Quality
        ctk.CTkLabel(set_frame, text="Quality:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        quality_menu = ctk.CTkOptionMenu(set_frame, values=["High", "Medium", "Low"])
        quality_menu.grid(row=1, column=1, padx=10, pady=10, sticky="e")

        # Row 2: Speed (NEW)
        ctk.CTkLabel(set_frame, text="Conversion Speed:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        speed_menu = ctk.CTkOptionMenu(set_frame, values=["Ultrafast", "Fast", "Medium", "Slow"])
        speed_menu.grid(row=2, column=1, padx=10, pady=10, sticky="e")
        speed_menu.set("Medium") # Default

        ctk.CTkLabel(set_frame, text="(Ultrafast = Faster but larger file size)", text_color="gray", font=("Arial", 10)).grid(row=3, column=0, columnspan=2, pady=(0,5))

        def update_options(first_path):
            try:
                ext = os.path.splitext(first_path)[1].lower()
                current_val = format_menu.get()
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.ico']:
                    format_menu.configure(values=img_formats)
                    if current_val not in img_formats: format_menu.set("PNG")
                    speed_menu.configure(state="disabled") # Speed irrelevant for images
                else:
                    format_menu.configure(values=vid_formats)
                    if current_val not in vid_formats: format_menu.set("MP4")
                    speed_menu.configure(state="normal")
            except: pass

        update_file_display()

        # --- Run Button ---
        def run_batch_convert():
            if not self.convert_files: return
            fmt = format_menu.get().split(" ")[0].lower()
            qual = quality_menu.get()
            spd = speed_menu.get()
            
            if len(self.convert_files) == 1:
                src = self.convert_files[0]
                name = os.path.splitext(os.path.basename(src))[0]
                save_path = filedialog.asksaveasfilename(initialfile=f"{name}_converted.{fmt}", defaultextension=f".{fmt}")
                if not save_path: return
                dialog.destroy()
                
                # FIX: Pass arguments in the exact order defined in _start_converter_thread
                # Order: src_list, dest, quality, speed, is_batch, target_fmt
                self._start_converter_thread([src], save_path, qual, spd, is_batch=False)

            else:
                dest_folder = filedialog.askdirectory(title="Select Output Folder")
                if not dest_folder: return
                dialog.destroy()
                
                # FIX: Pass arguments in the exact order defined in _start_converter_thread
                # Order: src_list, dest, quality, speed, is_batch, target_fmt
                self._start_converter_thread(self.convert_files, dest_folder, qual, spd, is_batch=True, target_fmt=fmt)

        ctk.CTkButton(dialog, text="Start Conversion", command=run_batch_convert, fg_color="#16A085", height=40).pack(fill="x", padx=20, pady=20)
        
        self.wait_window(dialog)
        self._resume_mini_preview()
        
    def _start_converter_thread(self, src_list, dest, quality, speed, is_batch=False, target_fmt=None):
            self.save_as_btn.configure(state="disabled")
            self.quick_save_btn.configure(state="disabled")
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            
            # --- TIMER SETUP ---
            self.convert_start_time = time.time()
            self.convert_total_items = len(src_list)
            self.convert_current_item = 0
            self.is_converting = True
            self._update_conversion_timer() # Start the UI timer loop
            
            threading.Thread(target=self._converter_worker, args=(src_list, dest, quality, speed, is_batch, target_fmt), daemon=True).start()
            
    def _start_processing_timer(self, action_name="Processing"):
        """Generic timer for Upscale, Interpolate, and Combine."""
        self.process_start_time = time.time()
        self.is_processing = True
        
        def _timer_loop():
            if self.is_processing:
                elapsed = int(time.time() - self.process_start_time)
                mins, secs = divmod(elapsed, 60)
                # Update button text: "Upscaling... (00:12)"
                self.save_as_btn.configure(text=f"{action_name}... ({mins:02}:{secs:02})")
                self.after(1000, _timer_loop)
        
        _timer_loop()

    def _update_conversion_timer(self):
            """Updates the button text with live timer and progress."""
            if self.is_converting:
                elapsed = int(time.time() - self.convert_start_time)
                mins, secs = divmod(elapsed, 60)
                
                # Text: "Processing 1/5... (00:12)"
                status_text = f"Processing {self.convert_current_item}/{self.convert_total_items}... ({mins:02}:{secs:02})"
                self.save_as_btn.configure(text=status_text)
                
                # Schedule next update in 1 second
                self.after(1000, self._update_conversion_timer)

  # IMPORTANT: The definition line MUST include 'speed'
    def _converter_worker(self, src_list, dest, quality, speed, is_batch, target_fmt):
        success_count = 0
        errors = []

        for i, src in enumerate(src_list):
            self.convert_current_item = i + 1 # Update counter for the timer
            
            try:
                # Determine Output Path
                if is_batch:
                    name = os.path.splitext(os.path.basename(src))[0].replace("_converted", "") 
                    out_path = os.path.join(dest, f"{name}_conv.{target_fmt}")
                else:
                    out_path = dest

                # Call Backend with Speed
                res, msg = universal_convert_backend(src, out_path, quality, speed)
                
                if res: 
                    success_count += 1
                else: 
                    errors.append(f"{os.path.basename(src)}: {msg}")
                    
            except Exception as e:
                errors.append(f"{os.path.basename(src)}: {str(e)}")

        # --- FINISH ---
        self.is_converting = False # Stop timer loop
        
        self.after(0, lambda: self.progress_bar.stop())
        
        def reset_ui():
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
            self.save_as_btn.configure(text="💾 Combine & Save As...", state="normal")
            if self.default_folder: 
                self.quick_save_btn.configure(state="normal")
        
        self.after(100, reset_ui)
        self.after(200, lambda: self._show_batch_results(success_count, len(src_list), errors, dest if is_batch else os.path.dirname(dest)))

    def _show_batch_results(self, success, total, errors, output_dir):
        msg = f"Processed {success}/{total} files successfully."
        
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:5]) # Show first 5 errors
            if len(errors) > 5: msg += "\n..."
            messagebox.showwarning("Batch Result", msg)
        else:
            if messagebox.askyesno("Complete", f"{msg}\n\nOpen output folder?"):
                self._open_file_system(output_dir)

    def _show_conversion_success(self, dest):
        if messagebox.askyesno("Success", f"Conversion Complete!\nSaved to: {os.path.basename(dest)}\n\nOpen file location?"):
            self._open_file_system(dest)
        
    def _add_clip_from_path(self, path, mark_new=False):
        if not os.path.exists(path): return
        try:
            meta = extract_clip_metadata(path)
            self.playlist_data.append({
                'path': path, 
                'thumb': meta['thumb'], 
                'name': os.path.basename(path), 
                'duration': meta['duration'], 
                'res': meta['resolution'], 
                'fps': meta['fps'], 
                'size_str': meta['size_str']
            })
            
            # Mark the new index for highlighting
            if mark_new:
                new_idx = len(self.playlist_data) - 1
                self.newly_added_indices.add(new_idx)
                
            self._update_total_duration()
            self._render_playlist()
            
            # Auto-scroll to bottom
            self.after(100, lambda: self.scroll_frame._parent_canvas.yview_moveto(1.0))
            
        except Exception as e:
            print(f"Error adding generated clip: {e}")

    def _open_gif_converter(self):
        if not self.playlist_data:
            messagebox.showwarning("Warning", "Please add clips to the playlist first.")
            return
        
        self._pause_mini_preview() # <--- PAUSE
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Batch GIF Converter")
        dialog.geometry("400x450")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="GIF Settings", font=("Arial", 18, "bold")).pack(pady=20)
        saved_fps = str(self.gif_settings.get("fps", 10))
        saved_scale = str(self.gif_settings.get("scale", 0.5))
        saved_speed = str(self.gif_settings.get("speed", 1.0))
        f1 = ctk.CTkFrame(dialog, fg_color="transparent")
        f1.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(f1, text="FPS (1-30):", width=100, anchor="w").pack(side="left")
        fps_entry = ctk.CTkEntry(f1, width=60)
        fps_entry.pack(side="right"); fps_entry.insert(0, saved_fps)
        f2 = ctk.CTkFrame(dialog, fg_color="transparent")
        f2.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(f2, text="Scale (0.1-1.0):", width=100, anchor="w").pack(side="left")
        scale_entry = ctk.CTkEntry(f2, width=60)
        scale_entry.pack(side="right"); scale_entry.insert(0, saved_scale)
        f3 = ctk.CTkFrame(dialog, fg_color="transparent")
        f3.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(f3, text="Speed Multiplier:", width=100, anchor="w").pack(side="left")
        speed_entry = ctk.CTkEntry(f3, width=60)
        speed_entry.pack(side="right"); speed_entry.insert(0, saved_speed)
        def run_conversion():
            try:
                fps = int(fps_entry.get()); scale = float(scale_entry.get()); speed = float(speed_entry.get())
                if not (1 <= fps <= 60): raise ValueError
                if not (0.1 <= scale <= 1.0): raise ValueError
                if not (0.1 <= speed <= 10.0): raise ValueError
                self.gif_settings = {"fps": fps, "scale": scale, "speed": speed}
                self._save_settings_to_file()
            except:
                messagebox.showerror("Error", "Invalid settings.\nFPS: 1-60\nScale: 0.1-1.0\nSpeed: 0.1-10.0"); return
            dest_folder = filedialog.askdirectory(title="Select Output Folder")
            if not dest_folder: return
            dialog.destroy()
            self._start_gif_thread(dest_folder, fps, scale, speed)
        ctk.CTkButton(dialog, text="Start Conversion", command=run_conversion, fg_color="#2ECC71").pack(pady=30)
        
        self.wait_window(dialog)    # <--- WAIT
        self._resume_mini_preview() # <--- RESUME

    def _start_gif_thread(self, folder, fps, scale, speed):
        self.progress_bar.set(0)
        self.save_as_btn.configure(text="Initializing...", state="disabled")
        self.quick_save_btn.configure(state="disabled")
        threading.Thread(target=self._gif_worker, args=(folder, fps, scale, speed), daemon=True).start()

    def _gif_worker(self, folder, fps, scale, speed):
        total = len(self.playlist_data)
        success_count = 0
        for i, item in enumerate(self.playlist_data):
            try:
                status_msg = f"Converting GIF {i+1}/{total}... ({total - (i+1)} Remaining)"
                self.after(0, lambda m=status_msg: self.save_as_btn.configure(text=m))
                name = os.path.splitext(item['name'])[0] + ".gif"
                out_path = os.path.join(folder, name)
                self.after(0, lambda p=(i/total): self.progress_bar.set(p))
                if convert_to_gif_backend(item['path'], out_path, fps, scale, speed): success_count += 1
            except: pass
        self.after(0, lambda: self.progress_bar.set(1.0))
        self.after(0, lambda: self.save_as_btn.configure(text="💾 Combine & Save As...", state="normal"))
        if self.default_folder: self.after(0, lambda: self.quick_save_btn.configure(state="normal"))
        self.after(0, lambda: self._on_gif_complete(folder, success_count, total))

    def _on_gif_complete(self, folder, success, total):
        msg = f"Converted {success}/{total} videos to GIF!"
        if messagebox.askyesno("Done", f"{msg}\n\nDo you want to preview the output folder?"): self._open_file_system(folder)

    def _handle_trim_result(self, new_path):
        if not new_path or not os.path.exists(new_path): return
        selected_clip = self.playlist_data[self.selected_index]
        if selected_clip['name'].startswith("TRIMMED-") or "TEMP_" in selected_clip['name']:
            try: os.remove(selected_clip['path'])
            except: pass
        new_meta = extract_clip_metadata(new_path)
        self.playlist_data[self.selected_index] = {'path': new_path, 'thumb': new_meta['thumb'], 'name': os.path.basename(new_path), 'duration': new_meta['duration'], 'res': new_meta['resolution'], 'fps': new_meta['fps'], 'size_str': new_meta['size_str']}
        messagebox.showinfo("Success", "Video Edited Successfully!")
        self._update_total_duration()
        self._render_playlist()
        self._select_item(self.selected_index) 

    def _render_playlist(self):
        self._force_background_bindings()
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        
        for idx, item in enumerate(self.playlist_data):
            # --- COLOR LOGIC ---
            bg_color = "transparent"
            border_color = "#2b2b2b"
            
            if idx == self.selected_index:
                bg_color = "#1f6aa5"        # Blue for selected
                border_color = "#1f6aa5"
            elif idx in self.newly_added_indices:
                border_color = "#2ECC71"    # Green Outline for new/finished
                bg_color = "#253b2f"        # Slight green tint background
            
            # Create Frame
            row = ctk.CTkFrame(self.scroll_frame, fg_color=bg_color, border_width=2, border_color=border_color)
            row.pack(fill="x", pady=2, padx=5)
            
            # --- Bindings (Same as before) ---
            def on_mouse_down(event, i=idx, w=row):
                self._flash_border(w, "cyan")
                self._on_item_click(i)
                self._on_drag_start(event, i) 
            
            def on_dbl_click(event, i=idx, w=row): 
                self._flash_border(w, "red")
                self._show_clip_details(i)
                return "break"
                
            def on_drag_motion(event): self._on_drag_motion(event)
            def on_delete_click(i=idx): self._remove_specific_clip(i)
            
            # --- UI Elements (Same as before) ---
            if item['thumb']:
                lbl_img = ctk.CTkLabel(row, text="", image=item['thumb'])
                lbl_img.pack(side="left", padx=5, pady=5)
                lbl_img.bind("<Button-1>", on_mouse_down)
                lbl_img.bind("<B1-Motion>", on_drag_motion)
                lbl_img.bind("<Double-Button-1>", on_dbl_click)
                
            lbl_text = ctk.CTkLabel(row, text=f"{idx + 1}. {item['name']}", text_color="white")
            lbl_text.pack(side="left", padx=10)
            
            # Add "NEW" label if applicable
            if idx in self.newly_added_indices:
                ctk.CTkLabel(row, text="[DONE]", text_color="#2ECC71", font=("Arial", 10, "bold")).pack(side="left", padx=5)

            del_btn = ctk.CTkButton(row, text="🗑️", width=30, fg_color="transparent", hover_color="#C0392B", command=on_delete_click)
            del_btn.pack(side="right", padx=5)
            
            # Bind remaining events
            row.bind("<Button-1>", on_mouse_down)
            row.bind("<B1-Motion>", on_drag_motion)
            row.bind("<Double-Button-1>", on_dbl_click)
            lbl_text.bind("<Button-1>", on_mouse_down)
            lbl_text.bind("<B1-Motion>", on_drag_motion)
            lbl_text.bind("<Double-Button-1>", on_dbl_click)
            
    def _remove_specific_clip(self, index):
        if 0 <= index < len(self.playlist_data):
            self.selected_index = index 
            self._remove_clip()

    def _add_clip(self):
        new_clips = filedialog.askopenfilenames(defaultextension=".mp4", filetypes=[("Video", "*.mp4 *.mov *.avi *.webm")])
        if new_clips:
            self.configure(cursor="watch"); self.update()
            for clip_path in new_clips:
                if os.path.exists(clip_path):
                    meta = extract_clip_metadata(clip_path)
                    self.playlist_data.append({'path': clip_path, 'thumb': meta['thumb'], 'name': os.path.basename(clip_path), 'duration': meta['duration'], 'res': meta['resolution'], 'fps': meta['fps'], 'size_str': meta['size_str']})
            self.configure(cursor="")
            self._update_total_duration()
            self._render_playlist()

    def _remove_clip(self):
        if 0 <= self.selected_index < len(self.playlist_data):
            self.current_anim_id += 1 
            if self.preview_job: self.after_cancel(self.preview_job)
            item = self.playlist_data[self.selected_index]
            if item['name'].startswith("TRIMMED-") and messagebox.askyesno("Delete", "Delete temp file?"):
                try: os.remove(item['path'])
                except: pass
            self.playlist_data.pop(self.selected_index)
            self.selected_index = -1
            self._recreate_preview_label(text="[No Clip Selected]")
            self._update_info_panel(None) # Clear info
            self.preview_cache = []
            self._update_total_duration()
            self._render_playlist()
        else: messagebox.showwarning("Warning", "Select a clip.")

    def _clear_list(self):
        self.current_anim_id += 1
        if self.preview_job: self.after_cancel(self.preview_job)
        for item in self.playlist_data:
            if item['name'].startswith("TRIMMED-"):
                try: os.remove(item['path'])
                except: pass
        self.playlist_data = []
        self.selected_index = -1
        self._recreate_preview_label(text="[No Clip Selected]")
        self._update_info_panel(None) 
        self.preview_cache = []
        self._update_total_duration()
        self._render_playlist()
        self._force_background_bindings()
        self.focus_set()

    def _move_clip(self, d):
        if 0 <= self.selected_index < len(self.playlist_data):
            new_i = self.selected_index + d
            if 0 <= new_i < len(self.playlist_data):
                self.playlist_data[self.selected_index], self.playlist_data[new_i] = self.playlist_data[new_i], self.playlist_data[self.selected_index]
                self.selected_index = new_i
                self._render_playlist()

    def _open_frame_extract_dialog(self):
        if not (0 <= self.selected_index < len(self.playlist_data)):
            messagebox.showwarning("Warning", "Please select a clip.")
            return
        
        self._pause_mini_preview() # <--- PAUSE

        defaults = {'folder': self.default_folder, 'name': self.default_name}
        popup = VideoEditorPopup(self, self.playlist_data[self.selected_index]['path'], 
                                 mode="extract", defaults=defaults, 
                                 use_vlc=self.use_vlc_fullscreen, 
                                 editor_height=self.editor_window_height)
        
        self.wait_window(popup)    # <--- WAIT
        self._resume_mini_preview() # <--- RESUME
        
    def _open_trim_dialog(self):
        if not (0 <= self.selected_index < len(self.playlist_data)):
            messagebox.showwarning("Warning", "Please select a clip.")
            return
        
        self._pause_mini_preview() # <--- PAUSE
        
        popup = VideoEditorPopup(self, self.playlist_data[self.selected_index]['path'], 
                                 mode="trim", callback=self._handle_trim_result, 
                                 use_vlc=self.use_vlc_fullscreen, 
                                 editor_height=self.editor_window_height)
        
        self.wait_window(popup)    # <--- WAIT FOR CLOSE
        self._resume_mini_preview() # <--- RESUME
        
    def _update_total_duration(self):
        total_seconds = 0
        for item in self.playlist_data:
            total_seconds += item.get('duration', 0)
        hours = int(total_seconds // 3600); minutes = int((total_seconds % 3600) // 60); seconds = int(total_seconds % 60)
        self.duration_label.configure(text=f"Total Duration: {hours:02}:{minutes:02}:{seconds:02}")

    def _open_file_system(self, filepath):
        try:
            if os.name == 'nt': os.startfile(filepath)
            elif os.uname().sysname == 'Darwin': subprocess.call(('open', filepath))
            else: subprocess.call(('xdg-open', filepath))
        except Exception as e: messagebox.showerror("Error", f"Could not open file: {e}")

    def _quick_combine(self):
        if not self.playlist_data: return
        if not self.default_folder: return
        filename = f"{self.default_name}_{int(time.time())}.mp4"
        output_path = os.path.join(self.default_folder, filename)
        self._start_combine_thread(output_path)

    def _combine_save_as(self):
        if not self.playlist_data:
            messagebox.showwarning("Warning", "Add clips first.")
            return
        output_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if output_path:
            self._start_combine_thread(output_path)

    def _start_combine_thread(self, output_path):
        self.quick_save_btn.configure(state="disabled")
        self.save_as_btn.configure(state="disabled")
        
        # 1. Start with determinate (since combine usually reports progress quickly)
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        
        # 2. Start Timer
        self._start_processing_timer("Combining")
        
        self.merge_logger = TkProgressBarLogger(update_callback=self._update_progress_bar_safe)
        files = [i['path'] for i in self.playlist_data]
        threading.Thread(target=self._combine_worker, args=(files, output_path, self.merge_logger), daemon=True).start()

    def _on_combine_finished(self, final_path, error_msg):
        # 3. Stop Timer
        self.is_processing = False
        
        self.save_as_btn.configure(state="normal", text="💾 Combine & Save As...")
        if self.default_folder: self.quick_save_btn.configure(state="normal")
        self.progress_bar.set(0)
        
        if error_msg:
            messagebox.showerror("Merge Failed", f"Error: {error_msg}")
            return
        if final_path:
            if messagebox.askyesno("Success", f"Video Merged Successfully!\nSaved to:\n{os.path.basename(final_path)}\n\nPreview now?"):
                if self.after_merge_action == "In-App Preview":
                    VideoEditorPopup(self, final_path, mode="view", start_fullscreen=True, use_vlc=self.use_vlc_fullscreen, editor_height=self.editor_window_height)
                else:
                    self._open_file_system(final_path)
            
            # Temp Cleanup
            temp_files = [i['path'] for i in self.playlist_data if i['name'].startswith("TRIMMED-") or "TEMP_" in i['name']]
            if temp_files and messagebox.askyesno("Cleanup", "Delete temp files created during editing?"):
                for t in temp_files:
                    try: os.remove(t)
                    except: pass

    def _on_item_click(self, index): self._select_item(index)
    def _on_drag_start(self, event, index):
        self.drag_source_idx = index; self._select_item(index); self.update_idletasks(); self.drag_source_idx = index; self._select_item(index)
    def _on_drag_motion(self, event):
            if self.drag_source_idx is None: return
            y = event.y_root; target_idx = -1; rows = self.scroll_frame.winfo_children()
            for i, row in enumerate(rows):
                r_y = row.winfo_rooty(); r_h = row.winfo_height()
                if r_y <= y <= r_y + r_h: target_idx = i; break
            if target_idx != -1 and target_idx != self.drag_source_idx:
                self.playlist_data[self.drag_source_idx], self.playlist_data[target_idx] = self.playlist_data[target_idx], self.playlist_data[self.drag_source_idx]
                self.selected_index = target_idx; self.drag_source_idx = target_idx; self._render_playlist()

    def _show_clip_details(self, index):
        if not (0 <= index < len(self.playlist_data)): return
        item = self.playlist_data[index]
        info_win = ctk.CTkToplevel(self); info_win.title("Clip Details"); info_win.geometry("400x400"); info_win.transient(self); info_win.grab_set()
        ctk.CTkLabel(info_win, text="Video Details", font=("Arial", 18, "bold")).pack(pady=15)
        details_frame = ctk.CTkFrame(info_win); details_frame.pack(fill="both", expand=True, padx=20, pady=10)
        def add_row(lbl, val):
            f = ctk.CTkFrame(details_frame, fg_color="transparent"); f.pack(fill="x", pady=5)
            ctk.CTkLabel(f, text=lbl, width=100, anchor="w", font=("Arial", 12, "bold")).pack(side="left", padx=10)
            ctk.CTkLabel(f, text=val, anchor="w", wraplength=200).pack(side="left", padx=10)
        add_row("File Name:", item['name']); add_row("Size:", item['size_str']); add_row("Duration:", f"{item.get('duration',0):.2f} sec")
        res = item.get('res', (0,0)); add_row("Resolution:", f"{res[0]}x{res[1]}"); add_row("FPS:", str(item.get('fps',0)))
        ctk.CTkLabel(details_frame, text="Full Path:", font=("Arial", 12, "bold"), anchor="w").pack(fill="x", padx=10, pady=(10,0))
        path_box = ctk.CTkTextbox(details_frame, height=60); path_box.pack(fill="x", padx=10, pady=5); path_box.insert("0.0", item['path']); path_box.configure(state="disabled")
        ctk.CTkButton(info_win, text="Close", command=info_win.destroy).pack(pady=15)

    def _load_preview_in_background(self, video_path, anim_id):
        with self.load_lock:
            if anim_id != self.current_anim_id: return
            pil_images, delay = get_preview_pil_images(video_path, duration=self.preview_duration, fps=self.preview_fps, height=self.preview_height)
            self.after(0, lambda: self._on_preview_loaded(pil_images, delay, anim_id))

    def _on_preview_loaded(self, pil_images, delay, anim_id):
        if anim_id != self.current_anim_id: return 
        if not pil_images: self._recreate_preview_label(text="[Preview Failed]"); return
        ctk_frames = []
        for img in pil_images: ctk_frames.append(ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height)))
        self.preview_cache = ctk_frames; self.preview_delay = delay; self.preview_idx = 0; self._animate_mini_preview(anim_id)
    
    # --- Preview Pause/Resume Helpers ---
    def _pause_mini_preview(self):
        """Stops the mini-player loop to save resources."""
        if self.preview_job:
            self.after_cancel(self.preview_job)
            self.preview_job = None

    def _resume_mini_preview(self):
        """Restarts the mini-player if a clip is selected and cached."""
        if self.preview_cache and not self.preview_job:
            self._animate_mini_preview(self.current_anim_id)

    def _update_info_panel(self, item):
        if not item:
            self.lbl_info_name.configure(text="---", text_color="#aaa"); self.lbl_info_size.configure(text="Size: --")
            self.lbl_info_res.configure(text="Res: --"); self.lbl_info_dur.configure(text="Duration: --"); return
        name = item.get('name', 'Unknown')
        if len(name) > 35: name = name[:32] + "..."
        res = item.get('res', (0,0)); dur = item.get('duration', 0); mins = int(dur // 60); secs = int(dur % 60)
        self.lbl_info_name.configure(text=name, text_color="white"); self.lbl_info_size.configure(text=f"Size: {item.get('size_str', '--')}")
        self.lbl_info_res.configure(text=f"Res: {res[0]}x{res[1]}"); self.lbl_info_dur.configure(text=f"Duration: {mins:02}:{secs:02}")

    def _select_item(self, index):
        # Clear the "New" status if this item was marked
        if index in self.newly_added_indices:
            self.newly_added_indices.remove(index)
            # We need to re-render to remove the green outline
            self.after(10, self._render_playlist)

        if self.selected_index == index: return 
        
        self.current_anim_id += 1
        self.selected_index = index
        self._render_playlist()
        if self.preview_job: self.after_cancel(self.preview_job); self.preview_job = None
        self._recreate_preview_label(text="Loading..."); self.preview_cache = [] 
        if 0 <= index < len(self.playlist_data):
            item = self.playlist_data[index]; self._update_info_panel(item) 
            if os.path.exists(item['path']): threading.Thread(target=self._load_preview_in_background, args=(item['path'], self.current_anim_id), daemon=True).start()
            else: self._recreate_preview_label(text="[File Not Found]")
        else:
            self._recreate_preview_label(text="[No Clip Selected]"); self._update_info_panel(None)

    def _animate_mini_preview(self, anim_id):
        if anim_id != self.current_anim_id: return
        if not self.preview_cache: return
        frame = self.preview_cache[self.preview_idx]
        try:
            self.mini_preview_label.configure(image=frame, text="")
            self.mini_preview_label.image = frame 
            self.preview_idx = (self.preview_idx + 1) % len(self.preview_cache)
            self.preview_job = self.after(self.preview_delay, lambda: self._animate_mini_preview(anim_id))
        except Exception: self.preview_job = None

    def _open_settings_dialog(self):
        
        self._pause_mini_preview() # <--- PAUSE
        
        dialog = ctk.CTkToplevel(self); dialog.title("Settings"); dialog.geometry("550x550"); dialog.transient(self); dialog.grab_set()
        tabview = ctk.CTkTabview(dialog); tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        tab_gen = tabview.add("General")
        tab_ai = tabview.add("AI Tools")
        tab_edit = tabview.add("Editor")
        tab_prev = tabview.add("Preview")
        tab_play = tabview.add("Playback")

        # --- GENERAL TAB ---
        ctk.CTkLabel(tab_gen, text="General Defaults", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        f_frame = ctk.CTkFrame(tab_gen); f_frame.pack(fill="x", padx=10, pady=5)
        self.lbl_folder = ctk.CTkLabel(f_frame, text=self.default_folder if self.default_folder else "No Folder Selected", text_color="gray")
        self.lbl_folder.pack(side="left", padx=10)
        ctk.CTkButton(f_frame, text="Browse Folder", width=100, command=self._browse_default_folder).pack(side="right", padx=10)
        n_frame = ctk.CTkFrame(tab_gen); n_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(n_frame, text="File Prefix:").pack(side="left", padx=10)
        self.entry_name = ctk.CTkEntry(n_frame, placeholder_text="output_video"); self.entry_name.pack(side="right", padx=10, fill="x", expand=True); self.entry_name.insert(0, self.default_name)
        ctk.CTkLabel(tab_gen, text="After Merge Action:", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        self.merge_action_menu = ctk.CTkOptionMenu(tab_gen, values=["System Player", "In-App Preview"]); self.merge_action_menu.pack(pady=5, padx=10, fill="x"); self.merge_action_menu.set(self.after_merge_action)

        # --- AI TOOLS TAB ---
        ctk.CTkLabel(tab_ai, text="External AI Engines Location", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        ctk.CTkLabel(tab_ai, text="Folder containing 'realesrgan-ncnn-vulkan' and 'rife-ncnn-vulkan'", text_color="gray", font=("Arial", 11)).pack(pady=(0, 10))
        
        ai_frame = ctk.CTkFrame(tab_ai)
        ai_frame.pack(fill="x", padx=10, pady=5)
        
        self.lbl_ai_dir = ctk.CTkLabel(ai_frame, text=self.ai_tools_dir if self.ai_tools_dir else "Default (Script Folder)", text_color="gray" if not self.ai_tools_dir else "white")
        self.lbl_ai_dir.pack(side="left", padx=10, fill="x", expand=True)
        
        def browse_ai_folder():
            d = filedialog.askdirectory()
            if d: 
                self.lbl_ai_dir.configure(text=d, text_color="white")
                self.temp_ai_dir_selection = d # Store temporarily
            
        ctk.CTkButton(ai_frame, text="Browse", width=80, command=browse_ai_folder).pack(side="right", padx=10)
        
        ctk.CTkButton(tab_ai, text="Reset to Default", fg_color="#555", height=24, command=lambda: self.lbl_ai_dir.configure(text="Default (Script Folder)", text_color="gray")).pack(pady=10)

        # --- EDITOR TAB ---
        ctk.CTkLabel(tab_edit, text="Editor Window Size", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        ed_frame = ctk.CTkFrame(tab_edit); ed_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(ed_frame, text="Base Preview Height (px):").pack(side="left", padx=10)
        self.entry_editor_height = ctk.CTkEntry(ed_frame, width=80); self.entry_editor_height.pack(side="right", padx=10); self.entry_editor_height.insert(0, str(self.editor_window_height))
        ctk.CTkLabel(ed_frame, text="Increase this if the editor is too small on your screen.", text_color="gray", font=("Arial", 10)).pack(pady=5)
        
        # --- PREVIEW TAB ---
        ctk.CTkLabel(tab_prev, text="Mini Preview Settings", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        fps_frame = ctk.CTkFrame(tab_prev); fps_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(fps_frame, text="Frame Rate (FPS):").pack(side="left", padx=10)
        self.entry_fps = ctk.CTkEntry(fps_frame, width=60); self.entry_fps.pack(side="right", padx=10); self.entry_fps.insert(0, str(self.preview_fps))
        res_frame = ctk.CTkFrame(tab_prev); res_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(res_frame, text="Height (pixels):").pack(side="left", padx=10)
        self.entry_height = ctk.CTkEntry(res_frame, width=60); self.entry_height.pack(side="right", padx=10); self.entry_height.insert(0, str(self.preview_height))
        dur_frame = ctk.CTkFrame(tab_prev); dur_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(dur_frame, text="Duration (sec):").pack(side="left", padx=10)
        self.entry_duration = ctk.CTkEntry(dur_frame, width=60); self.entry_duration.pack(side="right", padx=10); self.entry_duration.insert(0, str(self.preview_duration))
        
        # --- PLAYBACK TAB ---
        ctk.CTkLabel(tab_play, text="Playback Engine", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        self.vlc_var = ctk.BooleanVar(value=self.use_vlc_fullscreen)
        vlc_switch = ctk.CTkSwitch(tab_play, text="Use VLC for Fullscreen (High Performance)", variable=self.vlc_var); vlc_switch.pack(anchor="w", padx=20, pady=10)
        if not VLC_AVAILABLE: vlc_switch.configure(state="disabled", text="Use VLC (Not Installed)")
        ctk.CTkLabel(tab_play, text="If disabled, MoviePy will be used (slower, lower FPS).", text_color="gray", font=("Arial", 10)).pack(pady=5)
        
        # SAVE FUNCTION
        def save_and_close():
             # AI Dir
            current_txt = self.lbl_ai_dir.cget("text")
            if current_txt == "Default (Script Folder)":
                self.ai_tools_dir = ""
            elif hasattr(self, 'temp_ai_dir_selection') and self.temp_ai_dir_selection:
                 self.ai_tools_dir = self.temp_ai_dir_selection
            
            self._save_settings(dialog)

        ctk.CTkButton(dialog, text="Save & Close", command=save_and_close, fg_color="green").pack(pady=10)
        self.wait_window(dialog)    # <--- WAIT
        self._resume_mini_preview() # <--- RESUME

    def _browse_default_folder(self):
        d = filedialog.askdirectory()
        if d: self.default_folder = d; self.lbl_folder.configure(text=d, text_color="white")

    def _save_settings(self, dialog):
        self.default_name = self.entry_name.get()
        if not self.default_name: self.default_name = "output_video"
        try:
            fps_val = int(self.entry_fps.get()); 
            if 1 <= fps_val <= 60: self.preview_fps = fps_val
        except: pass
        try:
            h_val = int(self.entry_height.get()); 
            if 50 <= h_val <= 1080: self.preview_height = h_val
        except: pass
        try:
            d_val = float(self.entry_duration.get())
            if 0.5 <= d_val <= 60.0: self.preview_duration = d_val
        except: pass
        try:
            eh_val = int(self.entry_editor_height.get())
            if 300 <= eh_val <= 1200: self.editor_window_height = eh_val
        except: pass
        self.use_vlc_fullscreen = self.vlc_var.get(); self.after_merge_action = self.merge_action_menu.get()
        self._save_settings_to_file()
        if self.default_folder: self.quick_save_btn.configure(state="normal"); messagebox.showinfo("Settings", "Defaults saved!")
        else: self.quick_save_btn.configure(state="disabled")
        dialog.destroy()

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = VideoCombinerApp()
    app.mainloop()