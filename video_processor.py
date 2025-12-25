import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Tuple, Optional, List
from config import THUMB_WIDTH, THUMB_HEIGHT
from utils import format_size

logger = logging.getLogger(__name__)

# FFmpeg availability flags
FFMPEG_AVAILABLE = False
FFPROBE_AVAILABLE = False

def check_ffmpeg():
    """
    Enhanced FFmpeg check with multiple paths for Heroku
    """
    global FFMPEG_AVAILABLE, FFPROBE_AVAILABLE
    
    # Possible FFmpeg locations on Heroku
    possible_paths = [
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/app/.apt/usr/bin/ffmpeg',
        'ffmpeg'
    ]
    
    ffmpeg_path = None
    for path in possible_paths:
        if shutil.which(path) or os.path.exists(path):
            ffmpeg_path = path if os.path.exists(path) else shutil.which(path)
            break
    
    if not ffmpeg_path:
        ffmpeg_path = shutil.which('ffmpeg')
    
    if ffmpeg_path:
        try:
            result = subprocess.run(
                [ffmpeg_path, '-version'], 
                capture_output=True, 
                timeout=5
            )
            if result.returncode == 0:
                FFMPEG_AVAILABLE = True
                logger.info(f"✅ FFmpeg found at: {ffmpeg_path}")
                os.environ['FFMPEG_PATH'] = ffmpeg_path
        except Exception as e:
            logger.error(f"FFmpeg test failed: {e}")
    
    # Check ffprobe
    possible_probe_paths = [
        '/usr/bin/ffprobe',
        '/usr/local/bin/ffprobe',
        '/app/.apt/usr/bin/ffprobe',
        'ffprobe'
    ]
    
    ffprobe_path = None
    for path in possible_probe_paths:
        if shutil.which(path) or os.path.exists(path):
            ffprobe_path = path if os.path.exists(path) else shutil.which(path)
            break
    
    if not ffprobe_path:
        ffprobe_path = shutil.which('ffprobe')
    
    if ffprobe_path:
        try:
            result = subprocess.run(
                [ffprobe_path, '-version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                FFPROBE_AVAILABLE = True
                logger.info(f"✅ FFprobe found at: {ffprobe_path}")
                os.environ['FFPROBE_PATH'] = ffprobe_path
        except Exception as e:
            logger.error(f"FFprobe test failed: {e}")
    
    if not FFMPEG_AVAILABLE:
        logger.warning("⚠️ FFmpeg NOT available - Finalization will fail")
    if not FFPROBE_AVAILABLE:
        logger.warning("⚠️ FFprobe NOT available - Validation will fail")

# Run check on import
check_ffmpeg()

def get_ffmpeg_path():
    """Get FFmpeg path from environment or search"""
    return os.environ.get('FFMPEG_PATH', 'ffmpeg')

def get_ffprobe_path():
    """Get FFprobe path from environment or search"""
    return os.environ.get('FFPROBE_PATH', 'ffprobe')

def finalize_video(input_path: str) -> Optional[str]:
    """
    Finalize video by remuxing with ffmpeg.
    Standardizes format to mp4 and fixes seeking/duration issues.
    MANDATORY STEP per instructions.

    Command: ffmpeg -y -i INPUT -map 0 -c copy -movflags +faststart FINAL.mp4
    """
    if not FFMPEG_AVAILABLE:
        logger.warning("⚠️ FFmpeg not available, skipping finalization")
        return None

    ffmpeg = get_ffmpeg_path()

    # Create final filename
    base_name = os.path.basename(input_path)
    name, _ = os.path.splitext(base_name)
    dir_path = os.path.dirname(input_path)
    final_path = os.path.join(dir_path, f"FINAL_{name}.mp4")

    try:
        # 1. Primary Attempt: Standard Copy with Bitstream Filter
        cmd = [
            ffmpeg, '-y',
            '-i', input_path,
            '-map', '0',
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-movflags', '+faststart',
            final_path
        ]

        logger.info(f"🔄 Finalizing video (Attempt 1): {base_name}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=1800,
            env=os.environ.copy()
        )

        if result.returncode == 0 and os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
             logger.info(f"✅ Finalization success (Mode 1)")
             return final_path

        # 2. Fallback Attempt: Audio Transcode (Fixes codec issues causing segfaults)
        logger.warning(f"⚠️ Finalization failed (RC: {result.returncode}). Retrying with audio transcode...")

        cmd_fallback = [
            ffmpeg, '-y',
            '-i', input_path,
            '-map', '0',
            '-c:v', 'copy',     # Copy video
            '-c:a', 'aac',      # Re-encode audio to AAC
            '-movflags', '+faststart',
            final_path
        ]

        result_fb = subprocess.run(
            cmd_fallback,
            capture_output=True,
            timeout=1800,
            env=os.environ.copy()
        )

        if result_fb.returncode == 0 and os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
             logger.info(f"✅ Finalization success (Mode 2 - Audio Transcode)")
             return final_path

        logger.error(f"❌ All finalization attempts failed. Last RC: {result_fb.returncode}")

    except Exception as e:
        logger.error(f"❌ Finalization error: {e}")

    return None

def validate_video(filepath: str) -> bool:
    """
    Strict validation of video file using ffprobe.
    Checks duration (must not be empty, 0, or NaN).
    """
    if not FFPROBE_AVAILABLE:
        return False

    ffprobe = get_ffprobe_path()

    try:
        cmd = [
            ffprobe, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            env=os.environ.copy()
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            if output == 'N/A' or not output:
                logger.warning(f"❌ Validation failed: Duration is N/A or empty")
                return False

            try:
                duration = float(output)
                if duration <= 0 or duration != duration: # check for NaN
                     logger.warning(f"❌ Validation failed: Duration {duration}")
                     return False
                return True
            except ValueError:
                logger.warning(f"❌ Validation failed: Could not parse duration '{output}'")
                return False

    except Exception as e:
        logger.error(f"❌ Validation error: {e}")

    return False

def get_video_duration(filepath: str) -> int:
    """
    Get video duration strictly using ffprobe.
    Returns 0 if failed/invalid (to trigger fallback upstream).
    """
    if not os.path.exists(filepath):
        return 0

    if not FFPROBE_AVAILABLE:
        return 0

    ffprobe = get_ffprobe_path()
    
    try:
        cmd = [
            ffprobe, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            env=os.environ.copy()
        )
        
        if result.returncode == 0 and result.stdout.strip():
            duration_str = result.stdout.strip()
            if duration_str and duration_str != 'N/A':
                duration = float(duration_str)
                if duration > 0 and duration == duration: # Check > 0 and not NaN
                    return int(duration)
    except Exception as e:
        logger.debug(f"Duration check failed: {e}")
    
    return 0

def get_video_dimensions(filepath: str) -> Tuple[int, int]:
    """
    Get video width and height
    """
    if not FFPROBE_AVAILABLE:
        return 1280, 720
    
    ffprobe = get_ffprobe_path()
    
    try:
        cmd = [
            ffprobe, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            filepath
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            env=os.environ.copy()
        )
        
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            if ',' in output:
                w, h = output.split(',')
                width = int(w)
                height = int(h)
                
                if width > 0 and height > 0:
                    # Ensure even dimensions for encoding compatibility (if needed later)
                    width = width - (width % 2) if width % 2 else width
                    height = height - (height % 2) if height % 2 else height
                    return width, height
    except Exception as e:
        logger.debug(f"Dimensions extraction failed: {e}")
    
    return 1280, 720

def generate_thumbnail(video_path: str, thumb_path: str, duration: int = 0) -> bool:
    """
    Generate thumbnail strictly from FINAL.mp4
    Primary Method: ffmpeg -y -ss 00:00:03 -i FINAL.mp4 -frames:v 1 thumb.jpg
    """
    if not os.path.exists(video_path):
        return False
    
    if not FFMPEG_AVAILABLE:
        return False
    
    ffmpeg = get_ffmpeg_path()
    
    # Method 1: Mandatory Try (Strict Instruction)
    # ffmpeg -y -ss 00:00:03 -i FINAL.mp4 -frames:v 1 thumb.jpg
    
    try:
        cmd = [
            ffmpeg, '-y',
            '-ss', '00:00:12',
            '-i', video_path,
            '-frames:v', '1',
            '-q:v', '2',
            thumb_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            env=os.environ.copy()
        )

        if result.returncode == 0 and os.path.exists(thumb_path):
            size = os.path.getsize(thumb_path)
            if size > 1024:
                logger.info("✅ Thumbnail generated (Primary Method)")
                return True
    except Exception as e:
        logger.debug(f"Primary thumbnail method failed: {e}")

    # Method 2: Fallback (Try without seek if seek failed, or at 0s)
    try:
        cmd = [
            ffmpeg, '-y',
            '-i', video_path,
            '-frames:v', '1',
            '-q:v', '2',
            thumb_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            env=os.environ.copy()
        )

        if result.returncode == 0 and os.path.exists(thumb_path):
            size = os.path.getsize(thumb_path)
            if size > 1024:
                logger.info("✅ Thumbnail generated (Fallback Method)")
                return True
    except Exception as e:
        logger.debug(f"Fallback thumbnail method failed: {e}")

    return False

def split_video_file(video_path: str, max_size_mb: int = 1900) -> List[str]:
    """
    Split large video file using ffmpeg
    """
    if not FFMPEG_AVAILABLE:
        return [video_path]
    
    try:
        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size_mb <= max_size_mb:
            return [video_path]
        
        duration = get_video_duration(video_path)
        if duration <= 0:
            return [video_path]
        
        max_size_bytes = max_size_mb * 1024 * 1024
        num_parts = int(file_size / max_size_bytes) + 1
        split_duration = duration / num_parts
        
        base_name = os.path.basename(video_path)
        name, ext = os.path.splitext(base_name)
        dir_path = os.path.dirname(video_path)
        
        ffmpeg = get_ffmpeg_path()
        parts = []
        
        for i in range(num_parts):
            start_pos = i * split_duration
            part_name = f"{name}_part{i+1:03d}_of_{num_parts:03d}{ext}"
            part_path = os.path.join(dir_path, part_name)
            
            cmd = [
                ffmpeg, '-y',
                '-ss', str(start_pos),
                '-i', video_path,
                '-t', str(split_duration),
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                part_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=900,
                env=os.environ.copy()
            )
            
            if result.returncode == 0 and os.path.exists(part_path):
                parts.append(part_path)
            else:
                return [video_path] # Fallback to original if split fails
        
        if len(parts) >= 2:
            try:
                os.remove(video_path)
            except:
                pass
        
        return parts if parts else [video_path]
        
    except Exception:
        return [video_path]

def get_video_metadata(filepath: str) -> dict:
    """
    Get complete video metadata
    """
    duration = get_video_duration(filepath)
    width, height = get_video_dimensions(filepath)
    
    return {
        'duration': duration,
        'width': width,
        'height': height
    }
