import customtkinter as ctk
from tkinter import filedialog, Tk, PhotoImage
import threading
import os
import json
import time
from typing import List, Optional
from pathlib import Path
from PIL import Image, ImageTk
from video_processor import split_video, extract_audio, merge_videos, trim_video

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

APP_TITLE = "Video Splitter Pro"
APP_SIZE = "600x800" # Reduced height for better HD screen compatibility
COLOR_ACCENT = "#2CC985"
CONFIG_FILE = "config.json"

class VideoSplitterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Load configuration
        self.config = self.load_config()
        
        # Enable drag-and-drop if available
        if HAS_DND:
            TkinterDnD.Tk().withdraw()
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.on_drop)
        
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.resizable(True, True)
        
        # Center window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # Set minimum size to prevent UI from being squashed
        self.minsize(550, 700)
        
        self.file_queue: List[str] = []
        self.is_processing = False
        
        # Progress tracking variables
        self.process_start_time = None
        self.processed_bytes = 0
        self.total_bytes = 0
        
        # Thumbnail preview variables
        self.thumbnail_labels = []
        self.current_thumbnails = []
        
        # Apply theme from config
        self.apply_theme(self.config.get('theme', 'System'))
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.setup_ui()
        
        # Save config on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- CONFIGURATION METHODS ---
    
    def load_config(self) -> dict:
        """Load configuration from config.json file"""
        default_config = {
            'theme': 'System',
            'output_dir': '',
            'naming_pattern': '{name}_part{num}.{ext}',
            'split_mode': 'Count',
            'split_count': 5,
            'audio_format': 'mp3'
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    default_config.update(loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")
        
        return default_config
    
    def save_config(self):
        """Save current configuration to config.json file"""
        try:
            config_to_save = {
                'theme': self.theme_var.get(),
                'output_dir': self.entry_output.get(),
                'naming_pattern': self.entry_naming.get(),
                'split_mode': self.split_mode_var.get(),
                'split_count': int(self.slider.get()),
                'audio_format': self.audio_format_var.get()
            }
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def apply_theme(self, theme: str):
        """Apply the selected theme to the application"""
        if theme == 'Dark':
            ctk.set_appearance_mode("Dark")
        elif theme == 'Light':
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("System")
    
    def on_close(self):
        """Handle window close event - save config and destroy window"""
        self.save_config()
        self.destroy()
    
    # --- PROGRESS STATS METHODS ---
    
    def start_progress_tracking(self):
        """Initialize progress tracking variables"""
        self.process_start_time = time.time()
        self.processed_bytes = 0
        self.total_bytes = sum(os.path.getsize(f) for f in self.file_queue if os.path.exists(f))
    
    def update_progress_stats(self, progress: float):
        """Update progress statistics (ETA, speed, elapsed time)"""
        if self.process_start_time is None:
            return
        
        elapsed = time.time() - self.process_start_time
        
        # Update elapsed time label
        minutes, seconds = divmod(int(elapsed), 60)
        self.after(0, lambda: self.label_elapsed.configure(text=f"Elapsed: {minutes}:{seconds:02d}"))
        
        # Calculate speed and ETA
        if elapsed > 0 and progress > 0:
            # Calculate processing speed (bytes per second)
            current_processed = self.total_bytes * progress
            speed = current_processed / elapsed  # bytes per second
            
            # Convert to MB/s for display
            speed_mb = speed / (1024 * 1024)
            self.after(0, lambda: self.label_speed.configure(text=f"Speed: {speed_mb:.2f} MB/s"))
            
            # Calculate ETA
            if progress < 1.0:
                remaining_bytes = self.total_bytes - current_processed
                if speed > 0:
                    eta_seconds = remaining_bytes / speed
                    eta_minutes, eta_seconds = divmod(int(eta_seconds), 60)
                    if eta_minutes > 60:
                        eta_hours, eta_minutes = divmod(eta_minutes, 60)
                        self.after(0, lambda: self.label_eta.configure(text=f"ETA: {eta_hours}h {eta_minutes}m"))
                    else:
                        self.after(0, lambda: self.label_eta.configure(text=f"ETA: {eta_minutes}:{eta_seconds:02d}"))
                else:
                    self.after(0, lambda: self.label_eta.configure(text="ETA: --:--"))
            else:
                self.after(0, lambda: self.label_eta.configure(text="ETA: Done"))
        else:
            self.after(0, lambda: self.label_speed.configure(text="Speed: -- MB/s"))
            self.after(0, lambda: self.label_eta.configure(text="ETA: --:--"))
    
    def reset_progress_stats(self):
        """Reset progress statistics"""
        self.process_start_time = None
        self.processed_bytes = 0
        self.total_bytes = 0
        self.after(0, lambda: self.label_eta.configure(text="ETA: --:--"))
        self.after(0, lambda: self.label_speed.configure(text="Speed: -- MB/s"))
        self.after(0, lambda: self.label_elapsed.configure(text="Elapsed: 0:00"))

    def setup_ui(self):
        # Create main scrollable container
        self.frame_scrollable = ctk.CTkScrollableFrame(self, label_text="")
        self.frame_scrollable.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        # Header
        self.frame_header = ctk.CTkFrame(self.frame_scrollable, fg_color="transparent")
        self.frame_header.pack(fill="x", pady=(20, 10))
        ctk.CTkLabel(self.frame_header, text=APP_TITLE, font=("Roboto", 28, "bold")).pack()
        ctk.CTkLabel(self.frame_header, text="Advanced Video Processor", text_color="gray").pack()
        
        # Theme Toggle
        self.theme_var = ctk.StringVar(value=self.config.get('theme', 'System'))
        self.frame_theme = ctk.CTkFrame(self.frame_header, fg_color="transparent")
        self.frame_theme.pack(pady=(10, 0))
        ctk.CTkLabel(self.frame_theme, text="Theme:", text_color="gray").pack(side="left", padx=(0, 5))
        self.seg_theme = ctk.CTkSegmentedButton(
            self.frame_theme,
            values=["System", "Dark", "Light"],
            variable=self.theme_var,
            command=self.on_theme_change
        )
        self.seg_theme.pack(side="left")

        # Selection
        self.frame_file = ctk.CTkFrame(self.frame_scrollable, corner_radius=15)
        self.frame_file.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.frame_file, text="1. Select Videos", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        self.btn_select = ctk.CTkButton(self.frame_file, text="Choose Files...", command=self.select_files)
        self.btn_select.pack(padx=15, pady=(0, 10), fill="x")
        self.label_file_count = ctk.CTkLabel(self.frame_file, text="No files selected", text_color="gray")
        self.label_file_count.pack(padx=15, pady=(0, 15))

        # Output Directory
        ctk.CTkLabel(self.frame_file, text="Output Folder:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(5, 5))
        self.frame_output = ctk.CTkFrame(self.frame_file, fg_color="transparent")
        self.frame_output.pack(fill="x", padx=15, pady=(0, 15))
        
        self.entry_output = ctk.CTkEntry(self.frame_output, placeholder_text="Default: Same as video location")
        self.entry_output.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_browse_output = ctk.CTkButton(self.frame_output, text="Browse...", width=80, command=self.select_output_folder)
        self.btn_browse_output.pack(side="right")

        # Thumbnail Preview Section
        self.frame_thumbnails = ctk.CTkFrame(self.frame_scrollable, corner_radius=15)
        self.frame_thumbnails.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.frame_thumbnails, text="Video Thumbnails", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        # Scrollable thumbnail container
        self.frame_thumbnail_scroll = ctk.CTkScrollableFrame(self.frame_thumbnails, height=150)
        self.frame_thumbnail_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Placeholder text when no thumbnails
        self.label_no_thumbnails = ctk.CTkLabel(self.frame_thumbnail_scroll, text="No videos selected", text_color="gray")
        self.label_no_thumbnails.pack(pady=20)

        # Tabbed Interface for different modes
        self.tabview = ctk.CTkTabview(self.frame_scrollable, width=560, height=400)
        self.tabview.pack(fill="x", padx=20, pady=10)
        
        # Create tabs
        self.tab_split = self.tabview.add("Split")
        self.tab_audio = self.tabview.add("Extract Audio")
        self.tab_merge = self.tabview.add("Merge")
        self.tab_trim = self.tabview.add("Trim")
        
        # Setup each tab
        self.setup_split_tab()
        self.setup_audio_tab()
        self.setup_merge_tab()
        self.setup_trim_tab()

        # Action
        self.frame_action = ctk.CTkFrame(self.frame_scrollable, fg_color="transparent")
        self.frame_action.pack(fill="x", padx=20, pady=10)
        self.progress_bar = ctk.CTkProgressBar(self.frame_action, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        
        # Progress Stats Labels
        self.frame_stats = ctk.CTkFrame(self.frame_action, fg_color="transparent")
        self.frame_stats.pack(fill="x", pady=(0, 10))
        self.label_eta = ctk.CTkLabel(self.frame_stats, text="ETA: --:--", text_color="gray", font=("Roboto", 10))
        self.label_eta.pack(side="left", padx=(0, 20))
        self.label_speed = ctk.CTkLabel(self.frame_stats, text="Speed: -- MB/s", text_color="gray", font=("Roboto", 10))
        self.label_speed.pack(side="left", padx=(0, 20))
        self.label_elapsed = ctk.CTkLabel(self.frame_stats, text="Elapsed: 0:00", text_color="gray", font=("Roboto", 10))
        self.label_elapsed.pack(side="left")
        
        self.btn_run = ctk.CTkButton(self.frame_action, text="START PROCESS", command=self.start_batch_thread,
                                     fg_color=COLOR_ACCENT, hover_color="#229965", height=45, font=("Roboto", 16, "bold"))
        self.btn_run.pack(fill="x")
        self.label_status = ctk.CTkLabel(self.frame_action, text="Ready", text_color="gray")
        self.label_status.pack(pady=(5, 0))

        # Log
        self.frame_log = ctk.CTkFrame(self.frame_scrollable)
        self.frame_log.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.textbox_log = ctk.CTkTextbox(self.frame_log, font=("Consolas", 12))
        self.textbox_log.pack(fill="both", expand=True, padx=5, pady=5)

    # --- TAB SETUP METHODS ---

    def setup_split_tab(self):
        """Setup the Split tab with all split options"""
        # Split Mode Selection
        ctk.CTkLabel(self.tab_split, text="Split Mode:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(15, 5))
        self.split_mode_var = ctk.StringVar(value="Count")
        self.seg_split_mode = ctk.CTkSegmentedButton(
            self.tab_split,
            values=["Count", "Duration", "Size"],
            variable=self.split_mode_var,
            command=self.on_split_mode_change
        )
        self.seg_split_mode.pack(fill="x", padx=15, pady=(0, 10))

        # Count Mode - Slider
        self.frame_count_mode = ctk.CTkFrame(self.tab_split, fg_color="transparent")
        self.frame_count_mode.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(self.frame_count_mode, text="Split Count:").pack(side="left")
        self.label_slider_val = ctk.CTkLabel(self.frame_count_mode, text="5 Parts", font=("Roboto", 13, "bold"), text_color="#3B8ED0")
        self.label_slider_val.pack(side="right")
        self.slider = ctk.CTkSlider(self.tab_split, from_=2, to=20, number_of_steps=18, command=self.update_slider)
        self.slider.set(5)
        self.slider.pack(fill="x", padx=15, pady=(0, 15))

        # Duration Mode - Input
        self.frame_duration_mode = ctk.CTkFrame(self.tab_split, fg_color="transparent")
        ctk.CTkLabel(self.frame_duration_mode, text="Duration per Part (seconds):").pack(anchor="w", padx=15, pady=(5, 5))
        self.entry_duration = ctk.CTkEntry(self.frame_duration_mode, placeholder_text="e.g., 60")
        self.entry_duration.pack(fill="x", padx=15, pady=(0, 15))

        # Size Mode - Input
        self.frame_size_mode = ctk.CTkFrame(self.tab_split, fg_color="transparent")
        ctk.CTkLabel(self.frame_size_mode, text="Target Size per Part (MB):").pack(anchor="w", padx=15, pady=(5, 5))
        self.entry_size = ctk.CTkEntry(self.frame_size_mode, placeholder_text="e.g., 100")
        self.entry_size.pack(fill="x", padx=15, pady=(0, 15))

        # Precise Mode Checkbox
        self.var_precise_mode = ctk.IntVar(value=0)
        self.chk_precise_mode = ctk.CTkCheckBox(
            self.tab_split,
            text="Precise Mode (Re-encode for accuracy)",
            variable=self.var_precise_mode
        )
        self.chk_precise_mode.pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(self.tab_split, text="⚠ Slower but more accurate cuts", font=("Roboto", 10), text_color="gray").pack(anchor="w", padx=30, pady=(0, 15))

        # Custom Naming Pattern
        ctk.CTkLabel(self.tab_split, text="Naming Pattern:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(5, 5))
        self.entry_naming = ctk.CTkEntry(self.tab_split, placeholder_text="{name}_part{num}.{ext}")
        self.entry_naming.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkLabel(self.tab_split, text="Variables: {name}, {num}, {ext}", font=("Roboto", 10), text_color="gray").pack(anchor="w", padx=15, pady=(0, 15))

        # Archive Controls
        ctk.CTkLabel(self.tab_split, text="Output Format:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(5, 5))
        self.archive_mode_var = ctk.StringVar(value="One Zip")
        self.seg_button = ctk.CTkSegmentedButton(
            self.tab_split,
            values=["No Archive", "One Zip", "Zip Each Part"],
            variable=self.archive_mode_var,
            command=self.on_mode_change
        )
        self.seg_button.pack(fill="x", padx=15, pady=(0, 15))

        # Cleanup Option
        self.var_cleanup = ctk.IntVar(value=0)
        self.cb_cleanup = ctk.CTkCheckBox(
            self.tab_split, text="Delete raw .mp4 parts after zipping",
            variable=self.var_cleanup, state="normal"
        )
        self.cb_cleanup.pack(anchor="w", padx=15, pady=(0, 15))

    def setup_audio_tab(self):
        """Setup the Extract Audio tab"""
        ctk.CTkLabel(self.tab_audio, text="Audio Format:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(15, 5))
        self.audio_format_var = ctk.StringVar(value="mp3")
        self.seg_audio_format = ctk.CTkSegmentedButton(
            self.tab_audio,
            values=["mp3", "wav", "aac"],
            variable=self.audio_format_var
        )
        self.seg_audio_format.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(self.tab_audio, text="Extract audio from all selected videos", font=("Roboto", 11), text_color="gray").pack(anchor="w", padx=15)

    def setup_merge_tab(self):
        """Setup the Merge tab"""
        ctk.CTkLabel(self.tab_merge, text="Merge Videos", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.tab_merge, text="Combine multiple videos into one file", font=("Roboto", 11), text_color="gray").pack(anchor="w", padx=15, pady=(0, 15))
        ctk.CTkLabel(self.tab_merge, text="⚠ Videos must have same resolution and codec", font=("Roboto", 10), text_color="orange").pack(anchor="w", padx=15, pady=(0, 15))

    def setup_trim_tab(self):
        """Setup the Trim tab"""
        ctk.CTkLabel(self.tab_trim, text="Trim Videos", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        # Start Time
        ctk.CTkLabel(self.tab_trim, text="Start Time (seconds):", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(10, 5))
        self.entry_trim_start = ctk.CTkEntry(self.tab_trim, placeholder_text="e.g., 0")
        self.entry_trim_start.pack(fill="x", padx=15, pady=(0, 10))
        
        # End Time
        ctk.CTkLabel(self.tab_trim, text="End Time (seconds):", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(5, 5))
        self.entry_trim_end = ctk.CTkEntry(self.tab_trim, placeholder_text="e.g., 60")
        self.entry_trim_end.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(self.tab_trim, text="Trim each video to specified time range", font=("Roboto", 11), text_color="gray").pack(anchor="w", padx=15)

    # --- LOGIC ---

    def select_files(self):
        paths = filedialog.askopenfilenames(title="Select videos", filetypes=(("Video", "*.mp4 *.mov *.avi"), ("All", "*.*")))
        if paths:
            self.file_queue = list(paths)
            self.label_file_count.configure(text=f"{len(paths)} Videos Selected", text_color="white")
            self.log(f"Selected {len(paths)} files.")
            self.update_thumbnails()

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, folder)
            self.log(f"Output folder set to: {folder}")

    def on_drop(self, event):
        """Handle drag-and-drop file drops"""
        try:
            # Parse dropped files (tkinterdnd2 provides files as space-separated paths)
            dropped_files = event.data
            if dropped_files:
                # Handle both Windows (curly braces) and Unix paths
                if dropped_files.startswith('{') and dropped_files.endswith('}'):
                    dropped_files = dropped_files[1:-1]
                
                # Split by spaces and filter valid files
                file_paths = []
                for path in dropped_files.split():
                    path = path.strip('"{}')  # Remove quotes and braces
                    if os.path.isfile(path):
                        # Check if it's a video file
                        ext = os.path.splitext(path)[1].lower()
                        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv']:
                            file_paths.append(path)
                
                if file_paths:
                    self.file_queue = file_paths
                    self.label_file_count.configure(text=f"{len(file_paths)} Videos Selected", text_color="white")
                    self.log(f"Dropped {len(file_paths)} files.")
                    self.update_thumbnails()
                else:
                    self.log("No valid video files dropped.")
        except Exception as e:
            self.log(f"Error handling drop: {e}")

    def update_slider(self, val):
        self.label_slider_val.configure(text=f"{int(val)} Parts")

    def on_split_mode_change(self, value):
        if value == "Count":
            self.frame_count_mode.pack(fill="x", padx=15, pady=5)
            self.frame_duration_mode.pack_forget()
            self.frame_size_mode.pack_forget()
        elif value == "Duration":
            self.frame_count_mode.pack_forget()
            self.frame_duration_mode.pack(fill="x", padx=15, pady=5)
            self.frame_size_mode.pack_forget()
        else:  # Size mode
            self.frame_count_mode.pack_forget()
            self.frame_duration_mode.pack_forget()
            self.frame_size_mode.pack(fill="x", padx=15, pady=5)

    def on_mode_change(self, value):
        # Disable cleanup if "No Archive" is selected
        if value == "No Archive":
            self.cb_cleanup.deselect()
            self.cb_cleanup.configure(state="disabled")
        else:
            self.cb_cleanup.configure(state="normal")
    
    def on_theme_change(self, value):
        """Handle theme change event"""
        self.apply_theme(value)
        self.save_config()
    
    # --- THUMBNAIL PREVIEW METHODS ---
    
    def update_thumbnails(self):
        """Generate and display thumbnails for selected videos"""
        # Clear existing thumbnails
        for widget in self.frame_thumbnail_scroll.winfo_children():
            widget.destroy()
        
        if not self.file_queue:
            self.label_no_thumbnails = ctk.CTkLabel(self.frame_thumbnail_scroll, text="No videos selected", text_color="gray")
            self.label_no_thumbnails.pack(pady=20)
            return
        
        # Generate thumbnails for each video
        for idx, video_path in enumerate(self.file_queue):
            try:
                thumbnail_frame = ctk.CTkFrame(self.frame_thumbnail_scroll, fg_color="transparent")
                thumbnail_frame.pack(fill="x", pady=5, padx=5)
                
                # Generate thumbnail image
                thumbnail_image = self.generate_thumbnail(video_path)
                
                if thumbnail_image:
                    # Create label with thumbnail
                    img_label = ctk.CTkLabel(thumbnail_frame, image=thumbnail_image, text="")
                    img_label.image = thumbnail_image  # Keep reference
                    img_label.pack(side="left", padx=(0, 10))
                
                # Add filename label
                filename = os.path.basename(video_path)
                name_label = ctk.CTkLabel(
                    thumbnail_frame,
                    text=f"{idx+1}. {filename}",
                    font=("Roboto", 11),
                    anchor="w"
                )
                name_label.pack(side="left", fill="x", expand=True)
                
            except Exception as e:
                self.log(f"Error generating thumbnail for {video_path}: {e}")
    
    def generate_thumbnail(self, video_path: str, size: tuple = (120, 80)) -> Optional[ImageTk.PhotoImage]:
        """
        Generate a thumbnail image from video file.
        
        Args:
            video_path: Path to video file
            size: Thumbnail size (width, height)
            
        Returns:
            ImageTk.PhotoImage object or None if failed
        """
        try:
            from video_processor import FFMPEG_EXE
            import subprocess
            
            # Create temporary thumbnail file
            temp_thumb_path = os.path.join(
                os.path.dirname(video_path),
                f".thumb_{os.path.basename(video_path)}.jpg"
            )
            
            # Use FFMPEG to extract a frame at 1 second
            cmd = [
                FFMPEG_EXE,
                "-i", video_path,
                "-ss", "00:00:01.000",
                "-vframes", "1",
                "-vf", f"scale={size[0]}:{size[1]}",
                "-y",
                temp_thumb_path
            ]
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo
            )
            
            # Load and convert to PhotoImage
            if os.path.exists(temp_thumb_path):
                pil_image = Image.open(temp_thumb_path)
                photo_image = ImageTk.PhotoImage(pil_image)
                
                # Clean up temporary file
                try:
                    os.remove(temp_thumb_path)
                except OSError:
                    pass
                
                return photo_image
            
            return None
            
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            return None

    def log(self, msg):
        self.textbox_log.insert("end", f"> {msg}\n")
        self.textbox_log.see("end")

    def start_batch_thread(self):
        if not self.file_queue: return self.log("Error: No files selected.")
        self.is_processing = True
        self.btn_run.configure(state="disabled")
        self.start_progress_tracking()
        threading.Thread(target=self.run_batch, daemon=True).start()

    def run_batch(self):
        # Get current tab
        current_tab = self.tabview.get()
        
        # Get custom output directory (empty string means use default)
        custom_output_dir = self.entry_output.get().strip()

        def on_log(m): self.after(0, lambda: self.log(m))
        def on_prog(v):
            self.after(0, lambda: self.progress_bar.set(v))
            self.update_progress_stats(v)

        # Process based on selected tab
        try:
            if current_tab == "Split":
                self.run_split_mode(custom_output_dir, on_log, on_prog)
            elif current_tab == "Extract Audio":
                self.run_audio_mode(custom_output_dir, on_log, on_prog)
            elif current_tab == "Merge":
                self.run_merge_mode(custom_output_dir, on_log, on_prog)
            elif current_tab == "Trim":
                self.run_trim_mode(custom_output_dir, on_log, on_prog)
        finally:
            self.after(0, lambda: self.btn_run.configure(state="normal"))
            self.after(0, lambda: self.label_status.configure(text="Done"))
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.reset_progress_stats()

    def run_split_mode(self, custom_output_dir, on_log, on_prog):
        """Run split video processing"""
        split_mode = self.split_mode_var.get()
        mode_label = self.archive_mode_var.get()
        cleanup = (self.var_cleanup.get() == 1)
        precise_mode = (self.var_precise_mode.get() == 1)
        naming_pattern = self.entry_naming.get().strip()

        # Map UI label to Internal Mode
        mode_map = {
            "No Archive": "NONE",
            "One Zip": "BUNDLE",
            "Zip Each Part": "INDIVIDUAL"
        }
        internal_mode = mode_map.get(mode_label, "BUNDLE")

        for idx, fpath in enumerate(self.file_queue):
            fname = os.path.basename(fpath)
            self.after(0, lambda: self.label_status.configure(text=f"Processing {idx+1}/{len(self.file_queue)}: {fname}"))
            try:
                if split_mode == "Count":
                    parts = int(self.slider.get())
                    split_video(fpath, parts=parts, archive_mode=internal_mode, cleanup_raw=cleanup, precise_mode=precise_mode, output_dir=custom_output_dir, naming_pattern=naming_pattern, on_progress=on_prog, on_log=on_log)
                elif split_mode == "Duration":
                    duration_per_part = float(self.entry_duration.get())
                    split_video(fpath, duration_per_part=duration_per_part, archive_mode=internal_mode, cleanup_raw=cleanup, precise_mode=precise_mode, output_dir=custom_output_dir, naming_pattern=naming_pattern, on_progress=on_prog, on_log=on_log)
                else:  # Size mode
                    target_size_mb = float(self.entry_size.get())
                    split_video(fpath, target_size_mb=target_size_mb, archive_mode=internal_mode, cleanup_raw=cleanup, precise_mode=precise_mode, output_dir=custom_output_dir, naming_pattern=naming_pattern, on_progress=on_prog, on_log=on_log)
                on_log(f"Success: {fname}")
            except Exception as e:
                on_log(f"Failed: {fname} ({e})")

    def run_audio_mode(self, custom_output_dir, on_log, on_prog):
        """Run audio extraction processing"""
        audio_format = self.audio_format_var.get()
        
        for idx, fpath in enumerate(self.file_queue):
            fname = os.path.basename(fpath)
            self.after(0, lambda: self.label_status.configure(text=f"Extracting {idx+1}/{len(self.file_queue)}: {fname}"))
            try:
                extract_audio(fpath, output_format=audio_format, output_dir=custom_output_dir, on_progress=on_prog, on_log=on_log)
                on_log(f"Success: {fname}")
            except Exception as e:
                on_log(f"Failed: {fname} ({e})")

    def run_merge_mode(self, custom_output_dir, on_log, on_prog):
        """Run video merge processing"""
        if len(self.file_queue) < 2:
            on_log("Error: At least 2 videos required for merging")
            return
        
        # Determine output path
        if custom_output_dir:
            output_dir = Path(custom_output_dir).resolve()
        else:
            output_dir = Path(self.file_queue[0]).parent
        
        # Generate output filename
        output_filename = "merged_video.mp4"
        output_path = output_dir / output_filename
        
        try:
            merge_videos(self.file_queue, str(output_path), on_progress=on_prog, on_log=on_log)
            on_log(f"Success: Merged {len(self.file_queue)} videos")
        except Exception as e:
            on_log(f"Failed to merge: {e}")

    def run_trim_mode(self, custom_output_dir, on_log, on_prog):
        """Run video trim processing"""
        try:
            start_time = float(self.entry_trim_start.get())
            end_time = float(self.entry_trim_end.get())
        except ValueError:
            on_log("Error: Invalid time values")
            return
        
        precise_mode = (self.var_precise_mode.get() == 1)
        
        for idx, fpath in enumerate(self.file_queue):
            fname = os.path.basename(fpath)
            self.after(0, lambda: self.label_status.configure(text=f"Trimming {idx+1}/{len(self.file_queue)}: {fname}"))
            try:
                trim_video(fpath, start_time=start_time, end_time=end_time, output_dir=custom_output_dir, precise_mode=precise_mode, on_progress=on_prog, on_log=on_log)
                on_log(f"Success: {fname}")
            except Exception as e:
                on_log(f"Failed: {fname} ({e})")
        
        self.after(0, lambda: self.btn_run.configure(state="normal"))
        self.after(0, lambda: self.label_status.configure(text="Done"))
        self.after(0, lambda: self.progress_bar.set(1.0))