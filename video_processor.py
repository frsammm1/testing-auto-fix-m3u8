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
    
    # RELAXED CHECK: If we found a path, assume it works or try to verify
    if ffmpeg_path:
        FFMPEG_AVAILABLE = True
        os.environ['FFMPEG_PATH'] = ffmpeg_path
        logger.info(f"🎥 FFmpeg set to: {ffmpeg_path}")
        try:
            result = subprocess.run(
                [ffmpeg_path, '-version'], 
                capture_output=True, 
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"✅ FFmpeg verified at: {ffmpeg_path}")
            else:
                logger.warning(f"⚠️ FFmpeg version check returned non-zero: {result.returncode}")
        except Exception as e:
            logger.warning(f"⚠️ FFmpeg found but version check failed: {e}")

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
    
    # RELAXED CHECK
    if ffprobe_path:
        FFPROBE_AVAILABLE = True
        os.environ['FFPROBE_PATH'] = ffprobe_path
        logger.info(f"🎥 FFprobe set to: {ffprobe_path}")
        try:
            result = subprocess.run(
                [ffprobe_path, '-version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"✅ FFprobe verified at: {ffprobe_path}")
            else:
                logger.warning(f"⚠️ FFprobe version check returned non-zero: {result.returncode}")
        except Exception as e:
            logger.warning(f"⚠️ FFprobe found but version check failed: {e}")
    
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
    """
    if not FFMPEG_AVAILABLE:
        logger.warning("⚠️ FFmpeg not available, skipping finalization")
        if os.path.exists(input_path):
            return input_path
        return None

    ffmpeg = get_ffmpeg_path()

    base_name = os.path.basename(input_path)
    name, _ = os.path.splitext(base_name)
    dir_path = os.path.dirname(input_path)
    final_path = os.path.join(dir_path, f"FINAL_{name}.mp4")

    try:
        # 1. Primary Attempt: Standard Copy (Safer without forced bsf)
        # yt-dlp's 'remux_video': 'mp4' should have already cleaned the container.
        # This step acts as a sanity pass to ensure faststart and standard naming.
        cmd = [
            ffmpeg, '-y',
            '-i', input_path,
            '-map', '0',
            '-c', 'copy',
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

        # 2. Fallback Attempt: Audio Transcode with bsf (If Mode 1 failed)
        logger.warning(f"⚠️ Finalization failed (RC: {result.returncode}). Retrying with bitstream filter...")

        cmd_fallback = [
            ffmpeg, '-y',
            '-i', input_path,
            '-map', '0',
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
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
             logger.info(f"✅ Finalization success (Mode 2 - BSF)")
             return final_path

        # 3. Last Attempt: Full Re-encode of Audio
        logger.warning(f"⚠️ Mode 2 failed. Retrying with audio transcode...")

        cmd_aac = [
            ffmpeg, '-y',
            '-i', input_path,
            '-map', '0',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-movflags', '+faststart',
            final_path
        ]

        result_aac = subprocess.run(
            cmd_aac,
            capture_output=True,
            timeout=1800,
            env=os.environ.copy()
        )

        if result_aac.returncode == 0 and os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
             logger.info(f"✅ Finalization success (Mode 3 - Audio Transcode)")
             return final_path

        logger.error(f"❌ All finalization attempts failed. Last RC: {result_fb.returncode}")

        if os.path.exists(input_path) and os.path.getsize(input_path) > 1024:
            logger.warning("⚠️ Returning ORIGINAL file as finalization failed.")
            return input_path

    except Exception as e:
        logger.error(f"❌ Finalization error: {e}")
        if os.path.exists(input_path) and os.path.getsize(input_path) > 1024:
             return input_path

    return None

def validate_video(filepath: str) -> bool:
    """
    Relaxed validation.
    """
    if not os.path.exists(filepath):
        return False

    size = os.path.getsize(filepath)
    if size < 1024:
        return False

    if not FFPROBE_AVAILABLE:
        return True

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
                # Try secondary check (stream duration)
                cmd2 = [
                    ffprobe, '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    filepath
                ]
                result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=20, env=os.environ.copy())
                if result2.returncode == 0 and result2.stdout.strip() and result2.stdout.strip() != 'N/A':
                     return True

                logger.warning(f"⚠️ Validation warning: Duration is N/A. Allowing anyway.")
                return True

            try:
                duration = float(output)
                if duration <= 0:
                    logger.warning(f"⚠️ Validation warning: Duration {duration}. Allowing anyway.")
                return True
            except ValueError:
                logger.warning(f"⚠️ Validation warning: Could not parse duration. Allowing anyway.")
                return True

    except Exception as e:
        logger.error(f"❌ Validation error: {e}")
        return True

    return True

def get_video_duration(filepath: str) -> int:
    """
    Get video duration strictly using ffprobe.
    Returns 0 if failed/invalid.
    """
    if not os.path.exists(filepath):
        return 0

    if not FFPROBE_AVAILABLE:
        return 0

    ffprobe = get_ffprobe_path()
    
    try:
        # 1. Try Container Format Duration
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
                try:
                    duration = float(duration_str)
                    if duration > 0:
                        return int(duration)
                except:
                    pass

        # 2. Try Video Stream Duration
        cmd_stream = [
            ffprobe, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]
        result_stream = subprocess.run(
            cmd_stream,
            capture_output=True,
            text=True,
            timeout=20,
            env=os.environ.copy()
        )

        if result_stream.returncode == 0 and result_stream.stdout.strip():
            duration_str = result_stream.stdout.strip()
            if duration_str and duration_str != 'N/A':
                try:
                    duration = float(duration_str)
                    if duration > 0:
                        return int(duration)
                except:
                    pass

    except Exception as e:
        logger.debug(f"Duration check failed: {e}")

    # 3. Fallback: Parse ffmpeg -i output if ffprobe failed/missing
    # This is useful when ffprobe is missing or fails but ffmpeg works
    if FFMPEG_AVAILABLE:
        try:
            ffmpeg = get_ffmpeg_path()
            cmd_ffmpeg = [ffmpeg, '-i', filepath]

            # ffmpeg -i usually writes to stderr and exits with 1 if no output file
            result = subprocess.run(
                cmd_ffmpeg,
                capture_output=True,
                text=True,
                timeout=20,
                env=os.environ.copy()
            )

            # We look at stderr regardless of return code
            output = result.stderr
            if output:
                import re
                # Pattern: Duration: 00:00:00.00
                match = re.search(r'Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)', output)
                if match:
                    hours, minutes, seconds = match.groups()
                    total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    if total_seconds > 0:
                        logger.info(f"✅ Duration extracted via FFmpeg fallback: {total_seconds}")
                        return int(total_seconds)

        except Exception as e:
            logger.debug(f"FFmpeg fallback duration check failed: {e}")
    
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
                try:
                    width = int(w)
                    height = int(h)

                    if width > 0 and height > 0:
                        width = width - (width % 2) if width % 2 else width
                        height = height - (height % 2) if height % 2 else height
                        return width, height
                except:
                    pass
    except Exception as e:
        logger.debug(f"Dimensions extraction failed: {e}")
    
    return 1280, 720

def generate_thumbnail(video_path: str, thumb_path: str, duration: int = 0) -> bool:
    """
    Generate thumbnail strictly from FINAL.mp4
    """
    if not os.path.exists(video_path):
        return False
    
    if not FFMPEG_AVAILABLE:
        return False
    
    ffmpeg = get_ffmpeg_path()
    
    try:
        # Seek to 12s as per reference
        seek_time = '00:00:12'
        if duration > 0 and duration < 12:
            seek_time = '00:00:01'

        # Attempt 1: Fast Seek (Before input)
        cmd = [
            ffmpeg, '-y',
            '-ss', seek_time,
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

        if result.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1024:
            logger.info("✅ Thumbnail generated (Primary Method)")
            return True
    except Exception as e:
        logger.debug(f"Primary thumbnail method failed: {e}")

    # Attempt 2: Slow Seek (After input)
    try:
        cmd = [
            ffmpeg, '-y',
            '-i', video_path,
            '-ss', seek_time,
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

        if result.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1024:
            logger.info("✅ Thumbnail generated (Fallback Method)")
            return True
    except Exception as e:
        logger.debug(f"Fallback thumbnail method failed: {e}")

    # Attempt 3: Last Resort at 00:00:01
    try:
        logger.info("🔄 Trying last resort thumbnail at 1s...")
        cmd = [
            ffmpeg, '-y',
            '-i', video_path,
            '-ss', '00:00:01',
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

        if result.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1024:
            logger.info("✅ Thumbnail generated (Last Resort)")
            return True
    except Exception as e:
        logger.debug(f"Last resort thumbnail failed: {e}")

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
                return [video_path]
        
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
