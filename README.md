
# Media Studio Pro

**Media Studio Pro** is a powerful, portable Python-based GUI application designed for batch media conversion. It leverages the power of **FFmpeg** to handle video, audio, and image processing with a modern, sleek interface built on **PyQt6**.

# 🎬 Custom Video Combiner & AI Toolkit

A powerful, all-in-one desktop video utility built with **Python**, **CustomTkinter**, and **FFmpeg**. This tool allows for seamless video merging, AI-powered upscaling, frame interpolation, and advanced editing with a modern, dark-themed GUI.

## 🚀 Key Features

### 🎞️ Workspace & Playlist


**Drag & Drop Support**: Easily add multiple video files (MP4, MOV, AVI, WEBM, MKV) directly into the workspace.


* **Live Mini-Previews**: Hover or select a clip to see an animated thumbnail preview with configurable FPS and duration.
* **Playlist Management**: Reorder clips using a drag-and-drop interface or manual "Up/Down" buttons to set the perfect merge sequence.

### 🤖 AI-Powered Enhancements


**Rocket Upscaler**: Increase video and image resolution (2x or 4x) using the **Real-ESRGAN** engine for superior detail.


* **Face Enhancement**: Optional integration with CodeFormer to sharpen and fix facial details in low-res footage.
  
**Smooth/FPS Tool**: Achieve buttery-smooth motion using **RIFE AI** frame interpolation to double or quadruple your framerate.



### ✂️ Advanced Video Editing

* **In-App Trimmer**: Precisely set start and end points to crop or delete specific sections of a clip.
  
**VLC Playback**: High-performance fullscreen previewing powered by the VLC backend for smooth playback.


* **Frame Extraction**: Capture high-quality JPEG stills from any moment in your video with a "Quick Save" feature.

### 🔄 Universal Converter & Tools

* **Batch Format Conversion**: Convert multiple files simultaneously to MP4, MKV, AVI, MOV, WEBM, or MP3 (audio extraction).
* **GIF Tool**: Turn video clips into optimized GIFs with custom control over scale, speed, and framerate.
* **Resize & Crop**: Standardize resolutions (1080p, 720p, etc.) using "Fit" (letterbox), "Stretch," or "Crop to Fill" modes.

---

## 🛠️ Installation

### 1. Prerequisites

* **Python 3.10+**
* 
**FFmpeg**: Must be installed and added to your system PATH for fast processing.


* 
**VLC Media Player**: Required for the high-performance preview engine.



### 2. Auto-Setup

Run the provided batch file to create a virtual environment and install all Python dependencies (CustomTkinter, MoviePy, Pillow, etc.):

```bash
install_dependencies.bat

```



### 3. External AI Engines

To enable AI features, download the following executables and place them in your `bin` folder (or the directory specified in Settings):

* [Real-ESRGAN-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN/releases)
* [RIFE-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan/releases)

---

## 🖥️ Usage

1. 
**Launch**: Run `run_app.bat` to start the GUI.


2. **Add Media**: Drag files into the main window or use the **"Add Clip"** button.
3. **Edit**: Use the sidebar to access the **Trimmer**, **Upscaler**, or **Converter**.
4. **Combine**: Click **"Quick Combine"** to merge everything in your playlist using your default settings.

---

## ⚙️ Configuration

The app saves your preferences in `video_combiner_config.json`, including:

* **Default Output Path**: `C:/Users/Rafae/Documents/ComfyUI/output/combine clip`
* **AI Tools Directory**: Custom path for external `.exe` tools
* **Preview Settings**: Customizable height and duration for the mini-player.

---

Would you like me to generate a specific **"Getting Started"** guide for the AI upscaling feature?

---<img width="1440" height="993" alt="preview" src="https://github.com/user-attachments/assets/9777b38c-fdb4-4a0a-bcfa-aff544bd7617" />

