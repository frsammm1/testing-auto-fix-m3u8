import os
import ssl
import asyncio
import aiohttp
import aiofiles
import yt_dlp
import logging
import time
from pathlib import Path
from typing import Optional
from pyrogram.types import Message
from config import *
from utils import format_size, format_time, create_progress_bar, is_youtube_url, is_mpd_url, safe_edit

logger = logging.getLogger(__name__)

async def download_direct_file(
    url: str,
    output_path: str,
    progress_msg: Optional[Message],
    active: dict
) -> Optional[str]:
    """
    Download direct file (images, documents, direct videos)
    """
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=50,
            force_close=False
        )
        
        timeout = aiohttp.ClientTimeout(total=CONNECTION_TIMEOUT)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"❌ HTTP {response.status} for {url}")
                    return None
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                last_update_time = 0
                
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        if not active.get('running', False):
                            if os.path.exists(output_path):
                                os.remove(output_path)
                            logger.info("⛔ Download stopped by user")
                            return None
                        
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress
                        now = time.time()
                        if progress_msg and (now - last_update_time >= PROGRESS_UPDATE_INTERVAL):
                            last_update_time = now
                            try:
                                percent = (downloaded / total_size * 100) if total_size > 0 else 0
                                elapsed = now - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = int((total_size - downloaded) / speed) if speed > 0 else 0
                                bar = create_progress_bar(percent)
                                
                                await safe_edit(
                                    progress_msg,
                                    f"⏬ **DOWNLOADING**\n\n"
                                    f"{bar}\n\n"
                                    f"📦 {format_size(downloaded)} / {format_size(total_size)}\n"
                                    f"🚀 {format_size(int(speed))}/s\n"
                                    f"⏱️ ETA: {format_time(eta)}"
                                )
                            except Exception as e:
                                logger.debug(f"Progress update error: {e}")
                
                if os.path.exists(output_path):
                    logger.info(f"✅ Downloaded: {format_size(downloaded)}")
                    return output_path
                
        return None
        
    except asyncio.TimeoutError:
        logger.error("⏱️ Download timeout")
        return None
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        return None

async def download_video_ytdlp(
    url: str,
    output_path: str,
    progress_msg: Optional[Message],
    active: dict,
    download_progress: dict
) -> Optional[str]:
    """
    Download video using yt-dlp (for M3U8, streaming links)
    """
    try:
        def progress_hook(d):
            if not active.get('running', False):
                raise Exception("Cancelled by user")
            
            if d['status'] == 'downloading':
                try:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    speed = d.get('speed', 0) or 0
                    eta = d.get('eta', 0)
                    
                    if total > 0:
                        percent = (downloaded / total) * 100
                        
                        download_progress['percent'] = percent
                        download_progress['downloaded'] = downloaded
                        download_progress['total'] = total
                        download_progress['speed'] = speed
                        download_progress['eta'] = eta
                except Exception as e:
                    logger.debug(f"Progress hook error: {e}")
        
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'concurrent_fragment_downloads': MAX_WORKERS,
            'retries': MAX_RETRIES,
            'fragment_retries': MAX_RETRIES,
            'buffersize': CHUNK_SIZE,
            'http_chunk_size': 10485760,
            'hls_prefer_native': True,
            'progress_hooks': [progress_hook],
            'external_downloader': 'aria2c',
            'external_downloader_args': ['-x', '16', '-k', '1M']
        }
        
        logger.info(f"🎬 Starting yt-dlp download...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Wait for file to be fully written
        await asyncio.sleep(2)
        
        # Find output file
        if os.path.exists(output_path):
            logger.info(f"✅ yt-dlp download complete: {output_path}")
            return output_path
        
        # Check for alternative extensions
        for ext in ['.mp4', '.mkv', '.webm', '.avi']:
            alt_path = output_path + ext
            if os.path.exists(alt_path):
                logger.info(f"✅ Found alternative: {alt_path}")
                return alt_path
        
        # Try without extension
        base = os.path.splitext(output_path)[0]
        for ext in ['.mp4', '.mkv', '.webm']:
            test_path = base + ext
            if os.path.exists(test_path):
                logger.info(f"✅ Found: {test_path}")
                return test_path
        
        logger.error(f"❌ Output file not found")
        return None
        
    except Exception as e:
        logger.error(f"❌ yt-dlp error: {e}")
        return None

async def update_video_progress(
    progress_msg: Optional[Message],
    download_progress: dict,
    active: dict
):
    """Update video download progress"""
    if not progress_msg:
        return
    
    last_update_time = 0
    
    while active.get('running', False):
        try:
            now = time.time()
            if not download_progress or now - last_update_time < PROGRESS_UPDATE_INTERVAL:
                await asyncio.sleep(1)
                continue
            
            last_update_time = now
            percent = download_progress.get('percent', 0)
            downloaded = download_progress.get('downloaded', 0)
            total = download_progress.get('total', 0)
            speed = download_progress.get('speed', 0)
            eta = download_progress.get('eta', 0)
            
            bar = create_progress_bar(percent)

            await safe_edit(
                progress_msg,
                f"🎬 **VIDEO DOWNLOAD**\n\n"
                f"{bar}\n\n"
                f"📦 {format_size(downloaded)} / {format_size(total)}\n"
                f"🚀 {format_size(int(speed))}/s\n"
                f"⏱️ ETA: {format_time(int(eta))}"
            )
        except Exception as e:
            logger.debug(f"Progress update error: {e}")
        
        await asyncio.sleep(1)

async def download_video(
    url: str,
    filename: str,
    progress_msg: Optional[Message],
    active: dict
) -> Optional[str]:
    """
    Main video download function
    Detects type and uses appropriate method
    """
    output_path = str(DOWNLOAD_DIR / filename)
    
    try:
        # Check if failed URL (YouTube, MPD)
        if is_youtube_url(url) or is_mpd_url(url):
            logger.info("❌ Failed URL detected (YouTube/MPD)")
            return 'FAILED'
        
        # Detect if streaming or direct
        url_lower = url.lower()
        is_stream = any(x in url_lower for x in ['.m3u8', '.ts', '/hls/', 'master.m3u8', 'index.m3u8'])
        
        if is_stream:
            logger.info("📺 Streaming video detected (M3U8/HLS)")
            download_progress = {}
            
            # Start progress update task
            if progress_msg:
                progress_task = asyncio.create_task(
                    update_video_progress(progress_msg, download_progress, active)
                )
            
            # Download in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: asyncio.run(download_video_ytdlp(
                    url, output_path, progress_msg, active, download_progress
                ))
            )
            
            if progress_msg:
                try:
                    progress_task.cancel()
                except:
                    pass
            
            return result
        else:
            logger.info("🎬 Direct video download")
            return await download_direct_file(url, output_path, progress_msg, active)
        
    except Exception as e:
        logger.error(f"❌ Video download error: {e}")
        return None

async def download_image(
    url: str,
    filename: str,
    progress_msg: Optional[Message],
    active: dict
) -> Optional[str]:
    """Download image"""
    output_path = str(DOWNLOAD_DIR / filename)
    logger.info(f"🖼️ Downloading image: {filename}")
    return await download_direct_file(url, output_path, progress_msg, active)

async def download_document(
    url: str,
    filename: str,
    progress_msg: Optional[Message],
    active: dict
) -> Optional[str]:
    """Download document"""
    output_path = str(DOWNLOAD_DIR / filename)
    logger.info(f"📄 Downloading document: {filename}")
    return await download_direct_file(url, output_path, progress_msg, active)
