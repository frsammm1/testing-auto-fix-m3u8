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
from utils import format_size, format_time, create_progress_bar, safe_edit
from url_helper import process_url, is_youtube_url, is_mpd_url

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
    download_progress: dict,
    quality: str = None,
    extra_headers: dict = None
) -> Optional[str]:
    """
    Download video using yt-dlp (for M3U8, streaming links)
    Uses Aria2c with specific arguments matched to reference repo.
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
        
        # Parse quality for dynamic format string logic
        format_str = 'bestvideo+bestaudio/best'
        if quality:
            try:
                # Extract numeric height (e.g. 720 from "720p")
                h = int(''.join(filter(str.isdigit, quality)))
                # Logic from reference: b[height<=h]/bv[height<=h]+ba/b/bv+ba
                # Adding [ext=mp4] preference as per reference if youtube, but general otherwise
                format_str = f"b[height<={h}]/bv[height<={h}]+ba/b/bv+ba"
            except:
                pass

        # User Agent from reference
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'

        ydl_opts = {
            'format': format_str,
            'outtmpl': output_path, # Should end in .mp4 if possible, but we handle that via merge_output_format
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'concurrent_fragment_downloads': MAX_WORKERS,
            'retries': 25,
            'fragment_retries': 25,
            'socket_timeout': 50,
            'buffersize': CHUNK_SIZE,
            'http_chunk_size': 10485760,
            'hls_prefer_native': True,
            'progress_hooks': [progress_hook],
            'external_downloader': 'aria2c',
            'external_downloader_args': ['-x', '16', '-j', '32'],
            'remux_video': 'mp4',
            'http_headers': {
                'User-Agent': user_agent
            }
        }
        
        if extra_headers:
            ydl_opts['http_headers'].update(extra_headers)
        
        logger.info(f"🎬 Starting yt-dlp download (Quality: {quality or 'Best'})... URL: {url}")

        # Retry logic
        max_external_retries = 10 if any(x in url for x in ['visionias', 'penpencilvod']) else 3

        last_error = None
        for attempt in range(max_external_retries):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                last_error = None
                break
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ Download attempt {attempt+1} failed: {e}")
                if attempt < max_external_retries - 1:
                    await asyncio.sleep(5)

        if last_error:
            logger.error(f"❌ yt-dlp final error: {last_error}")
            # Don't return None yet, check if file exists (sometimes it succeeds despite error)

        # Wait for file write
        await asyncio.sleep(2)
        
        # Check output
        if os.path.exists(output_path):
            return output_path
        
        # Check alternatives
        base = os.path.splitext(output_path)[0]
        for ext in ['.mp4', '.mkv', '.webm', '.avi']:
            if os.path.exists(base + ext):
                return base + ext
        
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
    active: dict,
    quality: str = None,
    extra_headers: dict = None
) -> Optional[str]:
    """
    Main video download function
    """
    # Force .mp4 extension for filename if not present
    if not filename.lower().endswith('.mp4'):
        filename = os.path.splitext(filename)[0] + '.mp4'

    output_path = str(DOWNLOAD_DIR / filename)
    
    try:
        # 1. Process URL using new url_helper logic from reference repo
        final_url, options = await process_url(url, quality)

        if extra_headers:
            if 'http_headers' not in options:
                options['http_headers'] = {}
            options['http_headers'].update(extra_headers)

        # 2. Check for Manual Fail conditions (YouTube/MPD)
        # Note: We check AFTER processing because some processing might resolve to these
        if is_youtube_url(final_url) or is_mpd_url(final_url):
            logger.info(f"❌ Failed URL detected (YouTube/MPD): {final_url}")
            return 'FAILED'
        
        # 3. Detect stream type
        url_lower = final_url.lower()
        is_stream = any(x in url_lower for x in ['.m3u8', '.ts', '/hls/', 'master.m3u8', 'index.m3u8'])
        # Also treat everything that isn't clearly a direct file as a stream for yt-dlp to be safe,
        # or use yt-dlp for everything which is more robust (Reference repo uses yt-dlp for almost everything).
        # We will default to yt-dlp unless it's a very simple direct file download request.
        # But `downloader.py` in this repo separates them.
        # To be safe and follow reference repo "system", we should prefer yt-dlp for complex links.
        
        if is_stream or "classplus" in url_lower or "visionias" in url_lower or "appx" in url_lower:
             logger.info("📺 Streaming/Complex video detected")
             download_progress = {}

             if progress_msg:
                 progress_task = asyncio.create_task(
                     update_video_progress(progress_msg, download_progress, active)
                 )

             loop = asyncio.get_event_loop()
             result = await loop.run_in_executor(
                 None,
                 lambda: asyncio.run(download_video_ytdlp(
                     final_url, output_path, progress_msg, active, download_progress, quality, options.get('http_headers')
                 ))
             )

             if progress_msg:
                 try:
                     progress_task.cancel()
                 except:
                     pass

             return result
        else:
            # Fallback to direct download if simple, or yt-dlp if direct fails?
            # Let's try direct first for speed if it looks like a file.
            logger.info("🎬 Direct/Generic video download")
            res = await download_direct_file(final_url, output_path, progress_msg, active)
            if not res:
                # Fallback to yt-dlp
                logger.info("⚠️ Direct download failed, trying yt-dlp...")
                download_progress = {}
                return await download_video_ytdlp(
                     final_url, output_path, progress_msg, active, download_progress, quality, options.get('http_headers')
                )
            return res
        
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
