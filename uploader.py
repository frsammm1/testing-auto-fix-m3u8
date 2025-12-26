import os
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, List, Union
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from utils import format_size, format_time, create_progress_bar, safe_edit, safe_send
from video_processor import split_video_file, get_video_metadata, generate_thumbnail, get_video_duration
from config import UPLOAD_CHUNK_SIZE, SAFE_SPLIT_SIZE, DOWNLOAD_DIR, PROGRESS_UPDATE_INTERVAL

logger = logging.getLogger(__name__)

class UploadProgressTracker:
    def __init__(self, progress_msg: Message, part_num: int = 0, total_parts: int = 1):
        self.progress_msg = progress_msg
        self.part_num = part_num
        self.total_parts = total_parts
        self.last_update = 0
        self.start_time = time.time()
        self.speeds = []
    
    async def progress_callback(self, current: int, total: int):
        try:
            now = time.time()
            
            if now - self.last_update < PROGRESS_UPDATE_INTERVAL:  # Strict throttle
                return
            
            self.last_update = now
            
            percent = (current / total) * 100 if total > 0 else 0
            elapsed = now - self.start_time
            speed = current / elapsed if elapsed > 0 else 0
            
            self.speeds.append(speed)
            if len(self.speeds) > 5:
                self.speeds.pop(0)
            
            avg_speed = sum(self.speeds) / len(self.speeds)
            eta = int((total - current) / avg_speed) if avg_speed > 0 else 0
            
            bar = create_progress_bar(percent)
            
            part_info = ""
            if self.total_parts > 1:
                part_info = f"📊 Part {self.part_num}/{self.total_parts}\n"
            
            await safe_edit(
                self.progress_msg,
                f"📤 **UPLOADING**\n\n"
                f"{part_info}"
                f"{bar}\n\n"
                f"📦 {format_size(current)} / {format_size(total)}\n"
                f"🚀 {format_size(int(avg_speed))}/s\n"
                f"⏱️ ETA: {format_time(eta)}"
            )
        except:
            pass

async def upload_video(
    client: Client,
    chat_id: int,
    video_path: str,
    caption: str,
    progress_msg: Optional[Message],
    duration: int = 0,
    width: int = 0,
    height: int = 0,
    thumb_path: str = None
) -> Union[bool, int]:
    """
    Upload video with strict pipeline support.
    """
    try:
        # Check if file exists - addressing the crash from logs
        if not os.path.exists(video_path):
             logger.error(f"❌ Upload failed: File not found {video_path}")
             if progress_msg:
                 await safe_edit(progress_msg, "❌ Upload Failed: File missing")
             return False

        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        
        # Calculate metadata if missing (Reference repo style)
        if duration == 0 or width == 0 or height == 0:
            metadata = get_video_metadata(video_path)
            duration = metadata['duration']
            width = metadata['width']
            height = metadata['height']

        # Double check duration - if still 0, try one more time
        if duration == 0:
            logger.info("⚠️ Duration is 0, attempting forced recalculation...")
            duration = get_video_duration(video_path)
            logger.info(f"🔄 Recalculated duration: {duration}")

        # Generate thumbnail if missing (Reference repo style: 12th second)
        if not thumb_path or not os.path.exists(thumb_path):
             gen_thumb_path = str(DOWNLOAD_DIR / f"thumb_{os.getpid()}_{int(time.time())}.jpg")
             # Use video_processor which calls ffmpeg -ss 00:00:12
             if generate_thumbnail(video_path, gen_thumb_path, duration):
                 thumb_path = gen_thumb_path
             else:
                 logger.warning(f"⚠️ Thumbnail generation failed for {video_path}")
                 thumb_path = None

        # Check if split needed
        if file_size_mb > SAFE_SPLIT_SIZE:
            logger.info(f"🔪 File too large: {file_size_mb:.1f}MB, splitting...")
            if progress_msg:
                await safe_edit(
                    progress_msg,
                    f"🔪 **SPLITTING FILE**\n\n"
                    f"Size: {file_size_mb:.1f}MB\n"
                    f"Please wait..."
                )
            
            parts = split_video_file(video_path, SAFE_SPLIT_SIZE)
            
            if not parts or len(parts) == 0:
                return False
            
            # Upload each part
            first_message_id = 0
            for i, part_path in enumerate(parts, 1):
                if not os.path.exists(part_path):
                    continue
                
                # Recalculate metadata for part
                metadata = get_video_metadata(part_path)
                
                # Generate thumbnail for this part
                part_thumb_path = str(DOWNLOAD_DIR / f"thumb_part{i}_{os.getpid()}.jpg")
                has_thumb = generate_thumbnail(part_path, part_thumb_path, metadata['duration'])
                
                part_caption = f"{caption}\n\n📦 Part {i}/{len(parts)}"
                
                tracker = UploadProgressTracker(progress_msg, i, len(parts)) if progress_msg else None
                
                try:
                    sent_msg = await client.send_video(
                        chat_id=chat_id,
                        video=part_path,
                        caption=part_caption,
                        supports_streaming=True,
                        duration=metadata['duration'],
                        width=metadata['width'],
                        height=metadata['height'],
                        thumb=part_thumb_path if has_thumb else None,
                        progress=tracker.progress_callback if tracker else None
                    )
                    
                    if i == 1:
                        first_message_id = sent_msg.id
                    
                    logger.info(f"✅ Part {i} uploaded (msg_id: {sent_msg.id})")
                except FloodWait as e:
                    logger.warning(f"⏱️ FloodWait: {e.value}s")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    logger.error(f"Part {i} upload error: {e}")
                
                # Cleanup
                try:
                    os.remove(part_path)
                    if has_thumb:
                        os.remove(part_thumb_path)
                except:
                    pass
            
            # Clean up original file and thumbnail
            try:
                os.remove(video_path)
                if thumb_path and "thumb_" in thumb_path:
                    os.remove(thumb_path)
            except:
                pass

            return first_message_id if first_message_id > 0 else True
        
        else:
            # Single file upload
            tracker = UploadProgressTracker(progress_msg) if progress_msg else None
            
            sent_msg = await client.send_video(
                chat_id=chat_id,
                video=video_path,
                caption=caption,
                supports_streaming=True,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path,
                progress=tracker.progress_callback if tracker else None
            )
            
            try:
                os.remove(video_path)
                if thumb_path and "thumb_" in thumb_path:
                    os.remove(thumb_path)
            except:
                pass
            
            logger.info(f"✅ Video uploaded (msg_id: {sent_msg.id})")
            return sent_msg.id
        
    except FloodWait as e:
        logger.warning(f"⏱️ FloodWait: {e.value}s")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        # Fallback to document?
        # Reference repo falls back to document if video fails.
        if os.path.exists(video_path):
             logger.info("⚠️ Video upload failed, falling back to Document upload...")
             return await upload_document(client, chat_id, video_path, caption, progress_msg)
        else:
             return False

async def upload_photo(
    client: Client,
    chat_id: int,
    photo_path: str,
    caption: str,
    progress_msg: Optional[Message]
) -> Union[bool, int]:
    """
    Upload photo
    """
    try:
        tracker = UploadProgressTracker(progress_msg) if progress_msg else None
        
        sent_msg = await client.send_photo(
            chat_id=chat_id,
            photo=photo_path,
            caption=caption,
            progress=tracker.progress_callback if tracker else None
        )
        
        try:
            os.remove(photo_path)
        except:
            pass
        
        logger.info(f"✅ Photo uploaded (msg_id: {sent_msg.id})")
        return sent_msg.id
    except FloodWait as e:
        logger.warning(f"⏱️ FloodWait: {e.value}s")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        return False

async def upload_document(
    client: Client,
    chat_id: int,
    document_path: str,
    caption: str,
    progress_msg: Optional[Message]
) -> Union[bool, int]:
    """
    Upload document
    """
    try:
        file_size_mb = os.path.getsize(document_path) / (1024 * 1024)
        
        if file_size_mb > SAFE_SPLIT_SIZE:
            logger.info(f"🔪 Document too large: {file_size_mb:.1f}MB")
            
            chunk_size = int(SAFE_SPLIT_SIZE * 1024 * 1024)
            parts = []
            
            with open(document_path, 'rb') as source:
                part_num = 1
                while True:
                    chunk = source.read(chunk_size)
                    if not chunk:
                        break
                    
                    part_name = f"{os.path.basename(document_path)}.part{part_num:03d}"
                    part_path = str(DOWNLOAD_DIR / part_name)
                    
                    with open(part_path, 'wb') as part:
                        part.write(chunk)
                    
                    parts.append(part_path)
                    part_num += 1
            
            first_message_id = 0
            for i, part_path in enumerate(parts, 1):
                part_caption = f"{caption}\n\n📦 Part {i}/{len(parts)}"
                tracker = UploadProgressTracker(progress_msg, i, len(parts)) if progress_msg else None
                
                sent_msg = await client.send_document(
                    chat_id=chat_id,
                    document=part_path,
                    caption=part_caption,
                    progress=tracker.progress_callback if tracker else None
                )
                
                if i == 1:
                    first_message_id = sent_msg.id
                
                try:
                    os.remove(part_path)
                except:
                    pass
            
            try:
                os.remove(document_path)
            except:
                pass
            
            return first_message_id if first_message_id > 0 else True
        else:
            tracker = UploadProgressTracker(progress_msg) if progress_msg else None
            
            sent_msg = await client.send_document(
                chat_id=chat_id,
                document=document_path,
                caption=caption,
                progress=tracker.progress_callback if tracker else None
            )
            
            try:
                os.remove(document_path)
            except:
                pass
            
            logger.info(f"✅ Document uploaded (msg_id: {sent_msg.id})")
            return sent_msg.id
        
    except FloodWait as e:
        logger.warning(f"⏱️ FloodWait: {e.value}s")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        return False

async def send_failed_link(
    client: Client,
    chat_id: int,
    title: str,
    url: str,
    serial_num: int,
    file_type: str = "content"
) -> bool:
    """Send failed link message - Clickable Link Version"""
    try:
        emoji_map = {
            'video': '🎬',
            'image': '🖼️',
            'document': '📄'
        }
        
        emoji = emoji_map.get(file_type, '📦')
        
        # User requested: "clickable link hona chahiye... alag font me"
        # Removing code blocks from URL
        message = (
            f"❌ **MANUAL DOWNLOAD REQUIRED**\n\n"
            f"{emoji} **Item #{serial_num}**\n"
            f"📝 {title}\n\n"
            f"🔗 [Click Here to Download]({url})\n"
            f"**Link:** {url}\n\n"
            f"💡 Copy link and download manually"
        )
        
        await safe_send(
            client,
            chat_id=chat_id,
            text=message,
            disable_web_page_preview=False
        )
        
        return True
    except Exception as e:
        logger.error(f"Failed link send error: {e}")
        return False
