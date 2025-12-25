import re
import os
import asyncio
import logging
from typing import List, Dict, Optional, Union
from urllib.parse import urlparse
from pyrogram.errors import FloodWait
from pyrogram.types import Message, CallbackQuery
from config import SUPPORTED_TYPES

logger = logging.getLogger(__name__)

async def safe_send(client, chat_id, text, **kwargs):
    """Safe send_message wrapper handling FloodWait"""
    try:
        return await client.send_message(chat_id, text, **kwargs)
    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await safe_send(client, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"❌ safe_send error: {e}")
        return None

async def safe_reply(message: Message, text, **kwargs):
    """Safe reply_text wrapper handling FloodWait"""
    try:
        return await message.reply_text(text, **kwargs)
    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await safe_reply(message, text, **kwargs)
    except Exception as e:
        logger.error(f"❌ safe_reply error: {e}")
        return None

async def safe_edit(message: Message, text, **kwargs):
    """Safe edit_text wrapper handling FloodWait"""
    try:
        return await message.edit_text(text, **kwargs)
    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await safe_edit(message, text, **kwargs)
    except Exception as e:
        logger.error(f"❌ safe_edit error: {e}")
        return None

async def safe_answer(callback: CallbackQuery, text, **kwargs):
    """Safe answer wrapper handling FloodWait"""
    try:
        return await callback.answer(text, **kwargs)
    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await safe_answer(callback, text, **kwargs)
    except Exception as e:
        logger.error(f"❌ safe_answer error: {e}")
        return None

async def safe_send_document(client, chat_id, document, **kwargs):
    """Safe send_document wrapper handling FloodWait"""
    try:
        return await client.send_document(chat_id, document, **kwargs)
    except FloodWait as e:
        logger.warning(f"⏳ FloodWait: Sleeping {e.value}s")
        await asyncio.sleep(e.value + 1)
        return await safe_send_document(client, chat_id, document, **kwargs)
    except Exception as e:
        logger.error(f"❌ safe_send_document error: {e}")
        return None

def clean_title(text: str) -> str:
    """Clean title - remove : from middle"""
    if not text:
        return "Untitled"
    return str(text).replace(":", "-").strip()

def sanitize_filename(filename: str, max_length: int = 60) -> str:
    """Sanitize filename for safe file system usage"""
    safe = re.sub(r'[^\w\s-]', '', filename)
    safe = safe.replace(' ', '_')
    return safe[:max_length].strip('_')

def format_size(bytes_size: int) -> str:
    """Format bytes to human readable"""
    if bytes_size < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def format_time(seconds: int) -> str:
    """Format seconds to readable time"""
    if seconds < 0:
        return "0s"
    
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def create_progress_bar(percent: float, length: int = 20) -> str:
    """Create visual progress bar"""
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent:.1f}%"

def get_file_type(url: str) -> str:
    """Detect file type from URL"""
    url_lower = url.lower()
    
    # Video detection
    if any(ext in url_lower for ext in SUPPORTED_TYPES['video']):
        return 'video'
    
    # Image detection
    if any(ext in url_lower for ext in SUPPORTED_TYPES['image']):
        return 'image'
    
    # Document detection
    if any(ext in url_lower for ext in SUPPORTED_TYPES['document']):
        return 'document'
    
    # Default to video if uncertain
    if any(keyword in url_lower for keyword in ['/video/', 'stream', 'watch']):
        return 'video'
    
    return 'unknown'

def parse_txt_content(text: str) -> List[Dict]:
    """Parse TXT file content - Format: Title: URL"""
    lines = text.strip().split('\n')
    items = []
    
    for line in lines:
        line = line.strip()
        if not line or not (':' in line and ('http://' in line or 'https://' in line)):
            continue
        
        parts = line.split(':', 1)
        if len(parts) == 2:
            title = parts[0].strip()
            url = parts[1].strip()
            
            file_type = get_file_type(url)
            
            if file_type != 'unknown':
                items.append({
                    'title': title,
                    'url': url,
                    'type': file_type
                })
    
    return items

def parse_auto_content(text: str) -> List[Dict]:
    """Parse auto mode content - Format: [TOPIC] Title: URL"""
    lines = text.strip().split('\n')
    items = []
    
    for line in lines:
        line = line.strip()
        if not line or not (':' in line and ('http://' in line or 'https://' in line)):
            continue
        
        # Extract topic if present
        topic = ""
        if line.startswith('[') and ']' in line:
            topic_end = line.index(']')
            topic = line[1:topic_end].strip()
            line = line[topic_end+1:].strip()
        
        parts = line.split(':', 1)
        if len(parts) == 2:
            title = parts[0].strip()
            url = parts[1].strip()
            
            file_type = get_file_type(url)
            
            if file_type != 'unknown':
                items.append({
                    'title': title,
                    'url': url,
                    'type': file_type,
                    'topic': topic
                })
    
    return items

def is_youtube_url(url: str) -> bool:
    """Check if YouTube URL"""
    patterns = [
        r'youtube\.com/watch\?v=',
        r'youtu\.be/',
        r'youtube\.com/embed/',
        r'youtube\.com/shorts/'
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)

def is_mpd_url(url: str) -> bool:
    """Check if MPD URL"""
    return '.mpd' in url.lower() or '/manifest.' in url.lower()

def is_failed_url(url: str) -> bool:
    """Check if URL should fail (YouTube or MPD)"""
    return is_youtube_url(url) or is_mpd_url(url)

def count_content_types(items: List[Dict]) -> Dict:
    """Count different content types"""
    counts = {'video': 0, 'image': 0, 'document': 0}
    for item in items:
        ftype = item.get('type', 'unknown')
        if ftype in counts:
            counts[ftype] += 1
    return counts

def format_indian_time(time_str: str) -> Optional[str]:
    """
    Parse Indian time format (09:00 AM) to 24-hour format (09:00)
    """
    try:
        from datetime import datetime
        time_obj = datetime.strptime(time_str, "%I:%M %p")
        return time_obj.strftime("%H:%M")
    except:
        return None

def extract_channel_id(text: str) -> Optional[int]:
    """
    ✅ FIXED: Simple channel ID extraction - Returns numeric ID only
    
    Supports:
    - Standard format: -1001234567890
    - Without dash: 1001234567890
    - From t.me/c/ links
    """
    try:
        text = text.strip()
        
        # Remove formatting
        text = text.replace('`', '').replace('*', '').replace('_', '').replace(' ', '')
        
        logger.info(f"🔍 Extracting ID from: {text}")
        
        # Method 1: Standard format -100XXXXXXXXX
        if text.startswith('-100'):
            clean_text = text.replace('-', '').replace('+', '')
            if clean_text.isdigit() and len(clean_text) >= 10:
                channel_id = int('-' + clean_text)
                logger.info(f"✅ Extracted: {channel_id}")
                return channel_id
        
        # Method 2: Negative number format
        elif text.startswith('-') and text[1:].isdigit():
            channel_id = int(text)
            logger.info(f"✅ Extracted: {channel_id}")
            return channel_id
        
        # Method 3: From t.me/c/XXXXXX links
        match = re.search(r't\.me/c/(\d+)', text)
        if match:
            # Convert to proper -100XXXXXX format
            channel_id = int('-100' + match.group(1))
            logger.info(f"✅ Extracted from link: {channel_id}")
            return channel_id
        
        # Method 4: Pure numeric (assume needs -100 prefix)
        if text.isdigit() and len(text) >= 10:
            channel_id = int('-100' + text)
            logger.info(f"✅ Converted to: {channel_id}")
            return channel_id
        
        logger.error(f"❌ Invalid channel ID format: {text}")
        logger.error("💡 Use format: -1001234567890")
        return None
        
    except Exception as e:
        logger.error(f"❌ Channel ID extraction error: {e}")
        return None
