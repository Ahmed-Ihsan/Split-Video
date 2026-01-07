import os
import subprocess
import zipfile
import re
from pathlib import Path
from typing import Callable, List, Optional
import imageio_ffmpeg

# Resolve binary path once
def get_ffmpeg_binary() -> str:
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"

FFMPEG_EXE = get_ffmpeg_binary()

def get_video_duration(file_path: str) -> float:
    """
    Retrieves video duration using FFMPEG directly (No MoviePy).
    This is much faster and prevents 'loading' hangs.
    """
    cmd = [FFMPEG_EXE, "-i", file_path]
    
    # Hide window on Windows
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    # FFMPEG prints metadata to stderr, not stdout
    result = subprocess.run(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        startupinfo=startupinfo,
        text=True
    )
    
    # Regex to extract 'Duration: 00:00:00.00'
    duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", result.stderr)
    if duration_match:
        hours, minutes, seconds = map(float, duration_match.groups())
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds
    
    raise ValueError(f"Could not extract duration from FFMPEG. File might be corrupt: {file_path}")

def split_video(
    file_path: str,
    parts: int,
    archive_mode: str,
    cleanup_raw: bool,
    on_progress: Callable[[float], None],
    on_log: Callable[[str], None]
) -> None:
    
    input_path = Path(file_path).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Create isolated output directory
    safe_name = "".join([c for c in input_path.stem if c.isalnum() or c in (' ', '-', '_')]).strip()
    output_dir = input_path.parent / f"{safe_name}_splits"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generated_files: List[Path] = []

    try:
        # 1. Get Duration (Fast Method)
        on_log(f"Reading metadata: {input_path.name}...")
        duration = get_video_duration(str(input_path))
        part_duration = duration / parts
        
        on_log(f"Duration: {duration:.2f}s | Split into {parts} parts")

        # 2. Split Loop
        for i in range(parts):
            start_time = i * part_duration
            end_time = (i + 1) * part_duration
            if i == parts - 1: end_time = duration
            
            output_filename = f"{input_path.stem}_part{i+1}.mp4"
            output_file_path = output_dir / output_filename
            generated_files.append(output_file_path)
            
            cmd = [
                FFMPEG_EXE, "-y",
                "-i", str(input_path),
                "-ss", f"{start_time:.3f}",
                "-to", f"{end_time:.3f}",
                "-c", "copy",
                str(output_file_path)
            ]
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"FFMPEG Error: {process.stderr.decode('utf-8', errors='ignore')}")

            on_progress((i + 1) / parts)
            on_log(f"  > Created: {output_filename}")

        # 3. Archiving Logic
        if archive_mode == 'BUNDLE':
            archive_path = output_dir / f"{input_path.stem}_bundle.zip"
            on_log(f"Bundling all parts into {archive_path.name}...")
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_p in generated_files:
                    if file_p.exists(): zf.write(file_p, arcname=file_p.name)
        
        elif archive_mode == 'INDIVIDUAL':
            on_log("Zipping parts individually...")
            for file_p in generated_files:
                if file_p.exists():
                    zip_path = file_p.with_suffix('.zip')
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.write(file_p, arcname=file_p.name)

        # 4. Cleanup
        if cleanup_raw and archive_mode != 'NONE':
            on_log("Removing raw .mp4 parts...")
            for file_p in generated_files:
                try:
                    if file_p.exists(): file_p.unlink()
                except OSError: pass

    except Exception as e:
        on_log(f"CRITICAL ERROR: {str(e)}")
        raise e