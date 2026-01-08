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
    parts: Optional[int] = None,
    duration_per_part: Optional[float] = None,
    target_size_mb: Optional[float] = None,
    archive_mode: str = "BUNDLE",
    cleanup_raw: bool = False,
    precise_mode: bool = False,
    output_dir: Optional[str] = None,
    naming_pattern: Optional[str] = None,
    on_progress: Callable[[float], None] = lambda x: None,
    on_log: Callable[[str], None] = lambda x: None
) -> None:
    
    input_path = Path(file_path).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Validate parameters
    modes_provided = sum([
        parts is not None,
        duration_per_part is not None,
        target_size_mb is not None
    ])
    if modes_provided == 0:
        raise ValueError("Either 'parts', 'duration_per_part', or 'target_size_mb' must be specified")
    if modes_provided > 1:
        raise ValueError("Specify only one of: 'parts', 'duration_per_part', or 'target_size_mb'")

    # Create isolated output directory
    safe_name = "".join([c for c in input_path.stem if c.isalnum() or c in (' ', '-', '_')]).strip()
    
    # Use custom output directory if provided, otherwise use default (next to input file)
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_dir = output_path / f"{safe_name}_splits"
    else:
        output_dir = input_path.parent / f"{safe_name}_splits"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    on_log(f"Output directory: {output_dir}")
    
    generated_files: List[Path] = []

    try:
        # 1. Get Duration (Fast Method)
        on_log(f"Reading metadata: {input_path.name}...")
        duration = get_video_duration(str(input_path))
        
        # Calculate split parameters based on mode
        if parts is not None:
            part_duration = duration / parts
            on_log(f"Duration: {duration:.2f}s | Split into {parts} parts")
            total_parts = parts
        elif duration_per_part is not None:
            part_duration = duration_per_part
            total_parts = int(duration / duration_per_part) + (1 if duration % duration_per_part > 0 else 0)
            on_log(f"Duration: {duration:.2f}s | {duration_per_part}s per part = {total_parts} parts")
        else:  # target_size_mb is not None
            # Calculate based on file size
            file_size_bytes = input_path.stat().st_size
            file_size_mb = file_size_bytes / (1024 * 1024)
            target_size_bytes = target_size_mb * 1024 * 1024
            
            # Calculate approximate bitrate (bits per second)
            bitrate_bps = (file_size_bytes * 8) / duration
            
            # Calculate how many parts needed
            total_parts = int(file_size_mb / target_size_mb) + (1 if file_size_mb % target_size_mb > 0 else 0)
            
            # Calculate duration per part based on target size
            # size = bitrate * duration / 8
            # duration = size * 8 / bitrate
            part_duration = (target_size_bytes * 8) / bitrate_bps
            
            on_log(f"File Size: {file_size_mb:.2f}MB | Target: {target_size_mb:.2f}MB")
            on_log(f"Bitrate: {bitrate_bps/1024:.2f} kbps | {total_parts} parts @ {part_duration:.2f}s each")

        # 2. Split Loop
        for i in range(total_parts):
            start_time = i * part_duration
            end_time = (i + 1) * part_duration
            if i == total_parts - 1: end_time = duration
            
            # Generate output filename based on naming pattern or default
            if naming_pattern:
                # Use custom naming pattern with variables
                try:
                    output_filename = naming_pattern.format(
                        name=input_path.stem,
                        num=i+1,
                        ext=input_path.suffix[1:]  # Remove the dot from extension
                    )
                    # Ensure .mp4 extension if not present
                    if not output_filename.lower().endswith('.mp4'):
                        output_filename += '.mp4'
                except KeyError as e:
                    on_log(f"Warning: Invalid naming pattern variable {e}. Using default.")
                    output_filename = f"{input_path.stem}_part{i+1}.mp4"
            else:
                # Use default naming
                output_filename = f"{input_path.stem}_part{i+1}.mp4"
            
            output_file_path = output_dir / output_filename
            generated_files.append(output_file_path)
            
            # Build FFMPEG command
            if precise_mode:
                # Re-encode for precise cuts (slower but more accurate)
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-i", str(input_path),
                    "-ss", f"{start_time:.3f}",
                    "-to", f"{end_time:.3f}",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "fast",
                    "-crf", "23",
                    str(output_file_path)
                ]
                on_log(f"  > Re-encoding part {i+1} (Precise Mode)...")
            else:
                # Stream copy (fast, less precise)
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

            on_progress((i + 1) / total_parts)
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

def extract_audio(
    file_path: str,
    output_format: str = "mp3",
    output_dir: Optional[str] = None,
    on_progress: Callable[[float], None] = lambda x: None,
    on_log: Callable[[str], None] = lambda x: None
) -> None:
    """
    Extract audio from video file using FFMPEG.
    
    Args:
        file_path: Path to input video file
        output_format: Output audio format (mp3, wav, aac, etc.)
        output_dir: Custom output directory (optional)
        on_progress: Progress callback (0.0 to 1.0)
        on_log: Log callback for status messages
    """
    input_path = Path(file_path).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Determine output directory
    if output_dir:
        output_path = Path(output_dir).resolve()
    else:
        output_path = input_path.parent
    
    # Create output filename
    output_filename = f"{input_path.stem}.{output_format}"
    output_file_path = output_path / output_filename
    
    on_log(f"Extracting audio from {input_path.name}...")
    
    # Build FFMPEG command for audio extraction
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", str(input_path),
        "-vn",  # No video
        "-acodec", "libmp3lame" if output_format == "mp3" else "pcm_s16le",
        "-ab", "192k",
        "-ar", "44100",
        str(output_file_path)
    ]
    
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    try:
        process = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"FFMPEG Error: {process.stderr.decode('utf-8', errors='ignore')}")
        
        on_progress(1.0)
        on_log(f"Audio extracted: {output_filename}")
        
    except Exception as e:
        on_log(f"Error extracting audio: {str(e)}")
        raise e

def merge_videos(
    file_paths: List[str],
    output_path: str,
    on_progress: Callable[[float], None] = lambda x: None,
    on_log: Callable[[str], None] = lambda x: None
) -> None:
    """
    Merge multiple videos into one file using FFMPEG concat demuxer.
    
    Args:
        file_paths: List of input video file paths
        output_path: Path for output merged video
        on_progress: Progress callback (0.0 to 1.0)
        on_log: Log callback for status messages
    """
    if not file_paths:
        raise ValueError("No files provided for merging")
    
    # Create temporary concat list file
    concat_list_path = Path(output_path).parent / "concat_list.txt"
    
    try:
        # Write concat list file
        with open(concat_list_path, 'w', encoding='utf-8') as f:
            for file_path in file_paths:
                # Use absolute paths and escape special characters
                abs_path = Path(file_path).resolve()
                f.write(f"file '{abs_path}'\n")
        
        on_log(f"Created concat list with {len(file_paths)} files")
        
        # Build FFMPEG command for concat demuxer
        cmd = [
            FFMPEG_EXE, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(output_path)
        ]
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        on_log("Merging videos...")
        process = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"FFMPEG Error: {process.stderr.decode('utf-8', errors='ignore')}")
        
        on_progress(1.0)
        on_log(f"Merge complete: {Path(output_path).name}")
        
    except Exception as e:
        on_log(f"Error merging videos: {str(e)}")
        raise e
    finally:
        # Clean up temporary concat list
        if concat_list_path.exists():
            try:
                concat_list_path.unlink()
            except OSError:
                pass

def trim_video(
    file_path: str,
    start_time: float,
    end_time: float,
    output_dir: Optional[str] = None,
    precise_mode: bool = False,
    on_progress: Callable[[float], None] = lambda x: None,
    on_log: Callable[[str], None] = lambda x: None
) -> None:
    """
    Trim video to specified time range.
    
    Args:
        file_path: Path to input video file
        start_time: Start time in seconds
        end_time: End time in seconds
        output_dir: Custom output directory (optional)
        precise_mode: Whether to re-encode (slower but more accurate)
        on_progress: Progress callback (0.0 to 1.0)
        on_log: Log callback for status messages
    """
    input_path = Path(file_path).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Validate time range
    if start_time < 0:
        raise ValueError("Start time must be >= 0")
    if end_time <= start_time:
        raise ValueError("End time must be greater than start time")
    
    # Get video duration to validate
    duration = get_video_duration(str(input_path))
    if end_time > duration:
        on_log(f"Warning: End time ({end_time}s) exceeds video duration ({duration:.2f}s). Using {duration:.2f}s instead.")
        end_time = duration
    
    # Determine output directory
    if output_dir:
        output_path = Path(output_dir).resolve()
    else:
        output_path = input_path.parent
    
    # Create output filename
    output_filename = f"{input_path.stem}_trimmed.mp4"
    output_file_path = output_path / output_filename
    
    on_log(f"Trimming {input_path.name}: {start_time}s to {end_time}s")
    
    # Build FFMPEG command for trimming
    if precise_mode:
        # Re-encode for precise cuts
        cmd = [
            FFMPEG_EXE, "-y",
            "-i", str(input_path),
            "-ss", f"{start_time:.3f}",
            "-to", f"{end_time:.3f}",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            str(output_file_path)
        ]
        on_log("Re-encoding (Precise Mode)...")
    else:
        # Stream copy (fast)
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
    
    try:
        process = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"FFMPEG Error: {process.stderr.decode('utf-8', errors='ignore')}")
        
        on_progress(1.0)
        on_log(f"Trim complete: {output_filename}")
        
    except Exception as e:
        on_log(f"Error trimming video: {str(e)}")
        raise e