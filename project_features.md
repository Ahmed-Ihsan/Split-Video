# Project Features

## Core Functionality

### 1. Video Splitting
*   **Split Modes:**
    *   **By Count:** Split video into a specific number of equal parts (2-20 parts).
    *   **By Duration:** Split video into parts of a specific duration (in seconds).
    *   **By Size:** Split video into parts of a specific target file size (in MB).
*   **Processing Modes:**
    *   **Fast Mode (Default):** Uses stream copying for rapid splitting without re-encoding.
    *   **Precise Mode:** Re-encodes video for frame-accurate cuts (slower but more precise).
*   **Archiving & Cleanup:**
    *   **Bundle:** Zip all split parts into a single archive.
    *   **Individual:** Zip each split part into its own archive.
    *   **No Archive:** Keep files as raw video files.
    *   **Cleanup:** Option to automatically delete raw `.mp4` parts after archiving.
*   **Custom Naming:**
    *   Supports patterns using variables: `{name}` (original filename), `{num}` (part number), `{ext}` (extension).

### 2. Audio Extraction
*   Extract audio tracks from video files.
*   **Supported Formats:**
    *   MP3
    *   WAV
    *   AAC
*   Supports batch processing of multiple files.

### 3. Video Merging
*   Combine multiple video files into a single output file.
*   Uses FFMPEG concat demuxer (requires input files to have matching resolution and codecs).

### 4. Video Trimming
*   Trim specific sections of a video based on Start Time and End Time (in seconds).
*   Supports both Fast (stream copy) and Precise (re-encode) modes.

## User Interface (GUI)

### 1. File Management
*   **Selection:** Support for selecting multiple video files via system dialog.
*   **Drag & Drop:** Support for dragging and dropping files directly into the application (requires `tkinterdnd2`).
*   **Thumbnails:** Automatically generates and displays visual thumbnails for selected videos.
*   **Output Directory:** Option to specify a custom output folder or default to the source file's location.

### 2. Appearance & Usability
*   **Themes:** Switch between Light, Dark, and System themes.
*   **Responsive Design:** Resizable window with scrollable content areas.
*   **Status Information:** Real-time feedback including:
    *   Progress Bar
    *   Elapsed Time
    *   Processing Speed (MB/s)
    *   Estimated Time of Arrival (ETA)
*   **Activity Log:** Detailed scrollable log window showing process steps and errors.

### 3. Configuration & Persistence
*   **Settings Storage:** Automatically saves and loads user preferences (theme, output directory, split settings, naming patterns) to `config.json`.
*   **Window Management:** Remembers window position/state (handled by OS/framework standard behaviors, though config persistence focuses on app settings).

## Technical Implementation
*   **Framework:** Built using Python and `customtkinter` for a modern UI.
*   **Video Processing:** Powered by `FFMPEG` (via `imageio_ffmpeg` binary or system installation).
*   **Concurrency:** Uses threading to perform video operations in the background, keeping the GUI responsive during heavy processing.
