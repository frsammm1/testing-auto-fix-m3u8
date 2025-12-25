import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_DIR, QUALITY_PRESETS
from database import db
from utils import parse_txt_content, count_content_types, is_failed_url, safe_reply, safe_edit, safe_answer
from downloader import download_video, download_image, download_document
from uploader import upload_video, upload_photo, upload_document, send_failed_link
from video_processor import finalize_video, validate_video, get_video_duration, get_video_dimensions, generate_thumbnail

logger = logging.getLogger(__name__)

# Active downloads tracking
active_downloads = {}

async def start_manual_mode(client: Client, message: Message):
    """Start manual mode"""
    user_id = message.from_user.id
    
    await db.clear_user_session(user_id)
    
    await safe_reply(
        message,
        "📝 **MANUAL MODE ACTIVATED**\n\n"
        "📤 Send TXT file with links\n\n"
        "**Format:**\n"
        "`Title: URL`\n\n"
        "**Example:**\n"
        "`Video 1: https://example.com/video.m3u8`\n"
        "`Image 1: https://example.com/image.jpg`\n"
        "`Doc 1: https://example.com/file.pdf`\n\n"
        "✨ All link types supported!"
    )

async def handle_txt_file(client: Client, message: Message):
    """Handle TXT file upload"""
    user_id = message.from_user.id
    
    status = await safe_reply(message, "📥 Processing file...")
    
    try:
        # Download file
        file_path = await message.download(
            file_name=f"{DOWNLOAD_DIR}/{user_id}_input.txt"
        )
        
        # Read content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse content
        items = parse_txt_content(content)
        
        if not items:
            await safe_edit(status, "❌ No valid links found!")
            os.remove(file_path)
            return
        
        # Count types
        counts = count_content_types(items)
        
        # Save session
        await db.save_user_session(user_id, 'manual', {
            'items': items,
            'file_path': file_path,
            'step': 'select_range'
        })
        
        # Show options
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Range", callback_data="manual_range")],
            [InlineKeyboardButton("⬇️ Full", callback_data="manual_full")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
        ])
        
        await safe_edit(
            status,
            f"✅ **CONTENT DETECTED**\n\n"
            f"🎬 Videos: {counts['video']}\n"
            f"🖼️ Images: {counts['image']}\n"
            f"📄 Documents: {counts['document']}\n"
            f"📦 **Total: {len(items)}**\n\n"
            f"Choose action:",
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"TXT handling error: {e}")
        await safe_edit(status, f"❌ Error: {str(e)[:100]}")

async def handle_range_selection(client: Client, callback: CallbackQuery):
    """Handle range selection"""
    user_id = callback.from_user.id
    action = callback.data
    
    session = await db.get_user_session(user_id)
    if not session:
        await safe_answer(callback, "❌ Session expired!", show_alert=True)
        return
    
    items = session['data']['items']
    
    if action == "manual_full":
        # Process all
        session['data']['range'] = (1, len(items))
        session['data']['step'] = 'select_quality'
        await db.save_user_session(user_id, 'manual', session['data'])
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", callback_data="quality_480p"),
                InlineKeyboardButton("720p", callback_data="quality_720p")
            ],
            [InlineKeyboardButton("1080p (Original)", callback_data="quality_1080p")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_range")]
        ])
        
        await safe_edit(
            callback.message,
            f"📊 **Range: 1-{len(items)}** (All items)\n\n"
            f"🎬 **Select Quality:**\n\n"
            f"💡 1080p downloads original quality without conversion",
            reply_markup=kb
        )
    
    elif action == "manual_range":
        session['data']['step'] = 'range_input'
        await db.save_user_session(user_id, 'manual', session['data'])
        
        await safe_edit(
            callback.message,
            f"📊 **RANGE SELECTION**\n\n"
            f"Total items: {len(items)}\n\n"
            f"Send range in format:\n"
            f"• `1-50` → Items 1 to 50\n"
            f"• `10-20` → Items 10 to 20\n"
            f"• `5` → Only item 5\n\n"
            f"Or send `/cancel` to go back"
        )

async def handle_range_input(client: Client, message: Message):
    """Handle range input text"""
    user_id = message.from_user.id
    
    session = await db.get_user_session(user_id)
    if not session or session['data'].get('step') != 'range_input':
        return
    
    items = session['data']['items']
    text = message.text.strip()
    
    try:
        if '-' in text:
            start, end = map(int, text.split('-'))
        else:
            start = end = int(text)
        
        if start < 1 or end > len(items) or start > end:
            await safe_reply(message, f"❌ Invalid range! Use 1-{len(items)}")
            return
        
        session['data']['range'] = (start, end)
        session['data']['step'] = 'select_quality'
        await db.save_user_session(user_id, 'manual', session['data'])
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", callback_data="quality_480p"),
                InlineKeyboardButton("720p", callback_data="quality_720p")
            ],
            [InlineKeyboardButton("1080p (Original)", callback_data="quality_1080p")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_range")]
        ])
        
        count = end - start + 1
        await safe_reply(
            message,
            f"📊 **Range: {start}-{end}** ({count} items)\n\n"
            f"🎬 **Select Quality:**\n\n"
            f"💡 1080p downloads original quality without conversion",
            reply_markup=kb
        )
        
    except:
        await safe_reply(message, "❌ Invalid format! Use: `1-10` or `5`")

async def handle_quality_selection(client: Client, callback: CallbackQuery):
    """Handle quality selection and start processing"""
    user_id = callback.from_user.id
    quality = callback.data.split("_")[1]
    
    session = await db.get_user_session(user_id)
    if not session:
        await safe_answer(callback, "❌ Session expired!", show_alert=True)
        return
    
    items = session['data']['items']
    start, end = session['data']['range']
    selected_items = items[start-1:end]
    
    active_downloads[user_id] = {'running': True}
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⛔ Stop", callback_data="stop_download")]
    ])
    
    await safe_edit(
        callback.message,
        f"🚀 **PROCESSING STARTED**\n\n"
        f"⚡ Quality: {quality}\n"
        f"📊 Range: {start}-{end} ({len(selected_items)} items)\n\n"
        f"💪 Please wait...",
        reply_markup=kb
    )
    
    # Start processing
    await process_items(client, callback.message, selected_items, quality, start, end, user_id)
    
    # Cleanup
    try:
        os.remove(session['data']['file_path'])
    except:
        pass
    
    await db.clear_user_session(user_id)
    active_downloads.pop(user_id, None)

async def process_items(
    client: Client,
    message: Message,
    items: list,
    quality: str,
    start: int,
    end: int,
    user_id: int
):
    """Process and upload items"""
    success = 0
    failed = 0
    
    for idx, item in enumerate(items, start):
        if not active_downloads.get(user_id, {}).get('running', False):
            await safe_reply(message, "⛔ **STOPPED BY USER**")
            break
        
        prog = await safe_reply(
            message,
            f"📦 **Item {idx}/{end}**\n"
            f"📝 {item['title'][:50]}...\n"
            f"🚀 Processing..."
        )
        
        try:
            # Check if failed URL
            if is_failed_url(item['url']):
                await send_failed_link(
                    client, message.chat.id,
                    item['title'], item['url'], idx, item['type']
                )
                failed += 1
                await prog.delete()
                continue
            
            # Download
            file_path = None

            # STRICT PIPELINE VARIABLES
            video_duration = 0
            video_width = 0
            video_height = 0
            thumb_path = None

            if item['type'] == 'video':
                filename = sanitize_filename(item['title']) + '.mp4'
                raw_path = await download_video(
                    item['url'], filename, prog, active_downloads[user_id]
                )

                if raw_path and raw_path != 'FAILED':
                     # PIPELINE STEP 1: Finalize (Mandatory)
                    final_path = finalize_video(raw_path)

                    if final_path:
                        # PIPELINE STEP 2: Validate (Mandatory)
                        if validate_video(final_path):
                            file_path = final_path

                            # Collect Metadata from FINAL file
                            video_duration = get_video_duration(final_path)
                            video_width, video_height = get_video_dimensions(final_path)

                            # PIPELINE STEP 3: Thumbnail from FINAL file
                            thumb_filename = f"thumb_{idx}_{os.getpid()}.jpg"
                            generated_thumb_path = str(DOWNLOAD_DIR / thumb_filename)
                            if generate_thumbnail(final_path, generated_thumb_path, video_duration):
                                thumb_path = generated_thumb_path

                            try:
                                os.remove(raw_path)
                            except:
                                pass
                        else:
                            logger.warning("❌ Validation failed. Fallback to Document.")
                            item['type'] = 'document'
                            file_path = raw_path
                            try:
                                os.remove(final_path)
                            except:
                                pass
                    else:
                        logger.warning("❌ Finalization failed. Fallback to Document.")
                        item['type'] = 'document'
                        file_path = raw_path
                else:
                    file_path = raw_path

            elif item['type'] == 'image':
                ext = os.path.splitext(item['url'])[1] or '.jpg'
                filename = sanitize_filename(item['title']) + ext
                file_path = await download_image(
                    item['url'], filename, prog, active_downloads[user_id]
                )
            elif item['type'] == 'document':
                ext = os.path.splitext(item['url'])[1] or '.pdf'
                filename = sanitize_filename(item['title']) + ext
                file_path = await download_document(
                    item['url'], filename, prog, active_downloads[user_id]
                )
            
            if file_path == 'FAILED':
                await send_failed_link(
                    client, message.chat.id,
                    item['title'], item['url'], idx, item['type']
                )
                failed += 1
                await prog.delete()
                continue
            
            if not file_path or not os.path.exists(file_path):
                await send_failed_link(
                    client, message.chat.id,
                    item['title'], item['url'], idx, item['type']
                )
                failed += 1
                await prog.delete()
                continue
            
            # Upload
            caption = f"{idx}. {item['title']}"
            
            upload_success = False
            if item['type'] == 'video':
                upload_success = await upload_video(
                    client, message.chat.id, file_path, caption, prog,
                    duration=video_duration,
                    width=video_width,
                    height=video_height,
                    thumb_path=thumb_path
                )
            elif item['type'] == 'image':
                upload_success = await upload_photo(
                    client, message.chat.id, file_path, caption, prog
                )
            elif item['type'] == 'document':
                upload_success = await upload_document(
                    client, message.chat.id, file_path, caption, prog
                )
            
            if upload_success:
                success += 1
            else:
                failed += 1
            
            await prog.delete()
            
        except Exception as e:
            logger.error(f"Item {idx} error: {e}")
            failed += 1
            try:
                await prog.delete()
            except:
                pass
        
        await asyncio.sleep(0.3)
    
    await safe_reply(
        message,
        f"✅ **BATCH COMPLETE**\n\n"
        f"✔️ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {len(items)}\n"
        f"📍 Range: {start}-{end}"
    )

async def stop_download(client: Client, callback: CallbackQuery):
    """Stop download"""
    user_id = callback.from_user.id
    if user_id in active_downloads:
        active_downloads[user_id]['running'] = False
    await safe_answer(callback, "⛔ Stopping...", show_alert=True)
