import customtkinter as ctk
from gui import VideoSplitterApp

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

if __name__ == "__main__":
    app = VideoSplitterApp()
    app.mainloop()
