
# Media Studio Pro

**Media Studio Pro** is a powerful, portable Python-based GUI application designed for batch media conversion. It leverages the power of **FFmpeg** to handle video, audio, and image processing with a modern, sleek interface built on **PyQt6**.

## 🚀 Features

* **Batch Conversion**: Process multiple files simultaneously across different formats.
* **Intelligent Media Detection**: Automatically probes files to identify if they are video, audio, or images and suggests appropriate output formats.
* **Visual Previews**: Generates real-time thumbnails for videos, images, and extracts embedded album art from audio files.
* **Customizable Workflow**:
* **Rename Options**: Add custom prefixes or suffixes to output files.
* **Speed Control**: Toggle between `ultrafast`, `medium`, and `slow` presets to balance quality and conversion time.


* **Dynamic Theme Engine**: Change the application's accent colors on the fly with a built-in color picker.
* **Portable Design**: Built to run from a single directory without complex installation.

## 🛠️ Technical Stack

* **Frontend**: PyQt6
* **Backend**: Python 3.x
* **Engine**: FFmpeg / FFprobe (External binaries)
* **Styling**: Custom QSS (Qt Style Sheets) with a "Midnight" dark theme

## 📥 Installation

1. **Clone the Repository**:
```bash
git clone https://github.com/yourusername/media-studio-pro.git
cd media-studio-pro

```


2. **Install Dependencies**:
```bash
pip install PyQt6

```


3. **Setup FFmpeg**:
Ensure `ffmpeg.exe` and `ffprobe.exe` are placed in the root directory of the application (or are available in your system's PATH).

## 📖 How to Use

1. **Run the App**: Execute `python portable_converter.py`.
2. **Add Media**: Drag files into the "Media Queue" or use the **+ Add Files** button.
3. **Configure**: Select your desired output format and speed preset from the configuration panel.
4. **Set Destination**: Choose where you want your converted files to be saved.
5. **Convert**: Hit **Start Conversion** and watch the progress bar.

## 🎨 UI Customization

You can customize the look of Media Studio Pro by clicking the **🎨 Theme** button. This allows you to change the global accent color and gradient across the entire application interface.

---
