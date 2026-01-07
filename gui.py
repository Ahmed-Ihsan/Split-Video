import customtkinter as ctk
from tkinter import filedialog
import threading
import os
from typing import List
from video_processor import split_video

APP_TITLE = "Video Splitter Pro"
APP_SIZE = "600x850" # Slightly taller for new options
COLOR_ACCENT = "#2CC985"

class VideoSplitterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.resizable(True, True)
        self.file_queue: List[str] = []
        self.is_processing = False
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self.setup_ui()

    def setup_ui(self):
        # Header
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.grid(row=0, column=0, sticky="ew", pady=(20, 10))
        ctk.CTkLabel(self.frame_header, text=APP_TITLE, font=("Roboto", 28, "bold")).pack()
        ctk.CTkLabel(self.frame_header, text="Advanced Batch Splitter", text_color="gray").pack()

        # Selection
        self.frame_file = ctk.CTkFrame(self, corner_radius=15)
        self.frame_file.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(self.frame_file, text="1. Select Videos", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        self.btn_select = ctk.CTkButton(self.frame_file, text="Choose Files...", command=self.select_files)
        self.btn_select.pack(padx=15, pady=(0, 10), fill="x")
        self.label_file_count = ctk.CTkLabel(self.frame_file, text="No files selected", text_color="gray")
        self.label_file_count.pack(padx=15, pady=(0, 15))

        # Settings
        self.frame_settings = ctk.CTkFrame(self, corner_radius=15)
        self.frame_settings.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(self.frame_settings, text="2. Configure", font=("Roboto", 14, "bold")).pack(anchor="w", padx=15, pady=(15, 5))

        # Slider
        self.frame_slider = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        self.frame_slider.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(self.frame_slider, text="Split Count:").pack(side="left")
        self.label_slider_val = ctk.CTkLabel(self.frame_slider, text="5 Parts", font=("Roboto", 13, "bold"), text_color="#3B8ED0")
        self.label_slider_val.pack(side="right")
        self.slider = ctk.CTkSlider(self.frame_settings, from_=2, to=20, number_of_steps=18, command=self.update_slider)
        self.slider.set(5)
        self.slider.pack(fill="x", padx=15, pady=(0, 15))

        # --- NEW ARCHIVE CONTROLS ---
        ctk.CTkLabel(self.frame_settings, text="Output Format:", font=("Roboto", 13)).pack(anchor="w", padx=15, pady=(5, 5))
        
        # Segmented Button for clear mode selection
        self.archive_mode_var = ctk.StringVar(value="One Zip")
        self.seg_button = ctk.CTkSegmentedButton(
            self.frame_settings, 
            values=["No Archive", "One Zip", "Zip Each Part"],
            variable=self.archive_mode_var,
            command=self.on_mode_change
        )
        self.seg_button.pack(fill="x", padx=15, pady=(0, 15))

        # Cleanup Option
        self.var_cleanup = ctk.IntVar(value=0)
        self.cb_cleanup = ctk.CTkCheckBox(
            self.frame_settings, text="Delete raw .mp4 parts after zipping", 
            variable=self.var_cleanup, state="normal"
        )
        self.cb_cleanup.pack(anchor="w", padx=15, pady=(0, 15))

        # Action
        self.frame_action = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_action.grid(row=3, column=0, sticky="ew", padx=20, pady=10)
        self.progress_bar = ctk.CTkProgressBar(self.frame_action, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.btn_run = ctk.CTkButton(self.frame_action, text="START PROCESS", command=self.start_batch_thread, 
                                     fg_color=COLOR_ACCENT, hover_color="#229965", height=45, font=("Roboto", 16, "bold"))
        self.btn_run.pack(fill="x")
        self.label_status = ctk.CTkLabel(self.frame_action, text="Ready", text_color="gray")
        self.label_status.pack(pady=(5, 0))

        # Log
        self.frame_log = ctk.CTkFrame(self)
        self.frame_log.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.textbox_log = ctk.CTkTextbox(self.frame_log, font=("Consolas", 12))
        self.textbox_log.pack(fill="both", expand=True, padx=5, pady=5)

    # --- LOGIC ---

    def select_files(self):
        paths = filedialog.askopenfilenames(title="Select videos", filetypes=(("Video", "*.mp4 *.mov *.avi"), ("All", "*.*")))
        if paths:
            self.file_queue = list(paths)
            self.label_file_count.configure(text=f"{len(paths)} Videos Selected", text_color="white")
            self.log(f"Selected {len(paths)} files.")

    def update_slider(self, val):
        self.label_slider_val.configure(text=f"{int(val)} Parts")

    def on_mode_change(self, value):
        # Disable cleanup if "No Archive" is selected
        if value == "No Archive":
            self.cb_cleanup.deselect()
            self.cb_cleanup.configure(state="disabled")
        else:
            self.cb_cleanup.configure(state="normal")

    def log(self, msg):
        self.textbox_log.insert("end", f"> {msg}\n")
        self.textbox_log.see("end")

    def start_batch_thread(self):
        if not self.file_queue: return self.log("Error: No files selected.")
        self.is_processing = True
        self.btn_run.configure(state="disabled")
        threading.Thread(target=self.run_batch, daemon=True).start()

    def run_batch(self):
        parts = int(self.slider.get())
        mode_label = self.archive_mode_var.get()
        cleanup = (self.var_cleanup.get() == 1)

        # Map UI label to Internal Mode
        mode_map = {
            "No Archive": "NONE",
            "One Zip": "BUNDLE",
            "Zip Each Part": "INDIVIDUAL"
        }
        internal_mode = mode_map.get(mode_label, "BUNDLE")

        def on_log(m): self.after(0, lambda: self.log(m))
        def on_prog(v): self.after(0, lambda: self.progress_bar.set(v))

        for idx, fpath in enumerate(self.file_queue):
            fname = os.path.basename(fpath)
            self.after(0, lambda: self.label_status.configure(text=f"Processing {idx+1}/{len(self.file_queue)}: {fname}"))
            try:
                split_video(fpath, parts, internal_mode, cleanup, on_prog, on_log)
                on_log(f"Success: {fname}")
            except Exception as e:
                on_log(f"Failed: {fname} ({e})")
        
        self.after(0, lambda: self.btn_run.configure(state="normal"))
        self.after(0, lambda: self.label_status.configure(text="Done"))
        self.after(0, lambda: self.progress_bar.set(1.0))