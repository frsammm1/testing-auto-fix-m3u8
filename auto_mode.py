import logging
import asyncio
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from caption_styles import CAPTION_STYLES
from utils import extract_channel_id, format_indian_time, safe_edit, safe_reply, safe_answer, safe_send

logger = logging.getLogger(__name__)

_batch_manager = None

def set_batch_manager(manager):
    """Set batch manager instance"""
    global _batch_manager
    _batch_manager = manager
    logger.info("✅ Batch manager set")

async def start_auto_mode(client: Client, message: Message, user_id: int = None):
    """
    Start auto mode
    ✅ FIXED: Accepts user_id parameter to avoid bot ID confusion
    """
    if user_id is None:
        user_id = message.from_user.id
    
    logger.info(f"🔵 AUTO MODE for user: {user_id}")
    
    batches = await db.get_user_batches(user_id)
    
    buttons = []
    
    if batches:
        for batch in batches:
            status = "✅" if batch['is_active'] else "⏸️"
            buttons.append([InlineKeyboardButton(
                f"{status} {batch['batch_name'][:30]}",
                callback_data=f"batch_{batch['batch_id']}"
            )])
    else:
        buttons.append([InlineKeyboardButton("📝 No batches", callback_data="none")])
    
    buttons.append([InlineKeyboardButton("➕ Add Batch", callback_data="add_batch")])
    buttons.append([InlineKeyboardButton("➖ Remove Batch", callback_data="remove_batch")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_start")])
    
    kb = InlineKeyboardMarkup(buttons)
    
    text = (
        "🤖 **AUTO MODE**\n\n"
        "📦 Your Batches:\n\n"
        "✅ = Active | ⏸️ = Paused\n\n"
        "Select batch:"
    )
    
    # Try edit, fallback to reply
    msg = await safe_edit(message, text, reply_markup=kb)
    if not msg:
        await safe_reply(message, text, reply_markup=kb)

async def show_batch_settings(client: Client, callback: CallbackQuery, batch_id: str):
    """Show batch settings"""
    batch = await db.get_batch(batch_id)
    
    if not batch:
        await safe_answer(callback, "❌ Batch not found!", show_alert=True)
        return
    
    stats = await db.get_batch_stats(batch_id)
    
    text = (
        f"⚙️ **BATCH SETTINGS**\n\n"
        f"📦 **{batch['batch_name']}**\n\n"
        f"🎯 Destination: {batch['destination_id'] or 'Not set'}\n"
        f"🎬 Quality: {batch['quality'] or 'Not set'}\n"
        f"⏰ Schedule: {batch['schedule_time'] or 'Not set'} IST\n"
        f"📝 Caption: {batch['custom_caption'][:20] + '...' if batch['custom_caption'] else 'None'}\n"
        f"🎨 Style: {batch['caption_style'] or 'normal'}\n"
        f"📊 Sent: {stats['total_sent']}\n"
        f"📍 Status: {'Active ✅' if batch['is_active'] else 'Paused ⏸️'}\n\n"
        f"Choose action:"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Set Time", callback_data=f"settime_{batch_id}")],
        [InlineKeyboardButton("🎯 Set Chat", callback_data=f"setchat_{batch_id}")],
        [InlineKeyboardButton("🎬 Set Quality", callback_data=f"setquality_{batch_id}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{batch_id}")],
        [
            InlineKeyboardButton("💾 Backup", callback_data=f"backup_{batch_id}"),
            InlineKeyboardButton("📥 Restore", callback_data=f"restore_{batch_id}")
        ],
        [InlineKeyboardButton("📝 Caption", callback_data=f"setcaption_{batch_id}")],
        [InlineKeyboardButton("🎨 Style", callback_data=f"setstyle_{batch_id}")],
        [InlineKeyboardButton("⚠️ Reset", callback_data=f"reset_{batch_id}")],
        [InlineKeyboardButton("⏸️ Stop" if batch['is_active'] else "▶️ Start", 
                            callback_data=f"toggle_{batch_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_auto")]
    ])
    
    await safe_edit(callback.message, text, reply_markup=kb)

async def handle_add_batch(client: Client, callback: CallbackQuery):
    """Handle add batch"""
    user_id = callback.from_user.id
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'add_batch',
        'step': 'waiting_batch_id'
    })
    
    await safe_edit(
        callback.message,
        "➕ **ADD BATCH**\n\n"
        "Send batch ID (24 characters):\n"
        "`69204816dd258fd323a45956`\n\n"
        "Or /cancel"
    )

async def handle_batch_id_input(client: Client, message: Message, batch_id: str, batch_manager):
    """✅ FIXED: Add batch with correct user ID"""
    user_id = message.from_user.id
    
    logger.info(f"🔵 ADD BATCH for user {user_id}: {batch_id}")
    
    if not batch_id or len(batch_id) != 24:
        await safe_reply(message, "❌ Invalid batch ID! Must be 24 characters.")
        return
    
    existing = await db.get_batch(batch_id)
    if existing:
        await safe_reply(
            message,
            f"⚠️ **Batch Already Added!**\n\n"
            f"📦 {existing['batch_name']}\n"
            f"👤 Owner: {existing['user_id']}"
        )
        await db.clear_user_session(user_id)
        return
    
    status = await safe_reply(message, "🔍 Fetching batch...")
    
    try:
        result = await batch_manager.add_batch(batch_id, user_id)
        
        if result:
            await db.clear_user_session(user_id)
            await asyncio.sleep(0.5)
            
            batches = await db.get_user_batches(user_id)
            
            logger.info(f"✅ Fetched {len(batches)} batches for user {user_id}")
            
            buttons = []
            for batch in batches:
                status_icon = "✅" if batch['is_active'] else "⏸️"
                prefix = "🆕 " if batch['batch_id'] == batch_id else ""
                buttons.append([InlineKeyboardButton(
                    f"{prefix}{status_icon} {batch['batch_name'][:30]}",
                    callback_data=f"batch_{batch['batch_id']}"
                )])
            
            buttons.append([InlineKeyboardButton("➕ Add Another", callback_data="add_batch")])
            buttons.append([InlineKeyboardButton("➖ Remove Batch", callback_data="remove_batch")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_start")])
            
            kb = InlineKeyboardMarkup(buttons)
            
            await safe_edit(
                status,
                "🤖 **AUTO MODE**\n\n"
                "📦 Your Batches:\n\n"
                "🆕 = New | ✅ = Active | ⏸️ = Paused\n\n"
                f"✨ {result['batch_name']} added!\n\n"
                "Select batch:",
                reply_markup=kb
            )
        else:
            await safe_edit(status, "❌ Failed to fetch batch!")
            await db.clear_user_session(user_id)
            
    except Exception as e:
        logger.error(f"Add batch error: {e}", exc_info=True)
        await safe_edit(status, f"❌ Error: {str(e)[:100]}")
        await db.clear_user_session(user_id)

async def handle_remove_batch(client: Client, callback: CallbackQuery):
    """Handle remove batch"""
    user_id = callback.from_user.id
    batches = await db.get_user_batches(user_id)
    
    if not batches:
        await safe_answer(callback, "No batches!", show_alert=True)
        return
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'remove_batch',
        'step': 'select_batch',
        'batches': [{'id': b['batch_id'], 'name': b['batch_name']} for b in batches]
    })
    
    text = "➖ **REMOVE BATCH**\n\n"
    for idx, batch in enumerate(batches, 1):
        text += f"{idx}. {batch['batch_name']}\n"
    text += "\nSend number or /cancel"
    
    await safe_edit(callback.message, text)

async def handle_remove_batch_input(client: Client, message: Message, text: str):
    """Handle remove batch input"""
    user_id = message.from_user.id
    
    try:
        num = int(text.strip())
        
        session = await db.get_user_session(user_id)
        if not session or session['data'].get('action') != 'remove_batch':
            return
        
        batches = session['data'].get('batches', [])
        
        if num < 1 or num > len(batches):
            await safe_reply(message, f"❌ Invalid! Use 1-{len(batches)}")
            return
        
        batch = batches[num - 1]
        
        if _batch_manager:
            _batch_manager.stop_batch(batch['id'])
        
        await db.remove_batch(batch['id'])
        
        success_msg = await safe_reply(
            message,
            f"✅ **Batch Removed!**\n\n"
            f"📦 {batch['name']}\n\n"
            f"Refreshing..."
        )
        
        await db.clear_user_session(user_id)
        await asyncio.sleep(0.5)
        
        remaining = await db.get_user_batches(user_id)
        
        buttons = []
        if remaining:
            for b in remaining:
                status = "✅" if b['is_active'] else "⏸️"
                buttons.append([InlineKeyboardButton(
                    f"{status} {b['batch_name'][:30]}",
                    callback_data=f"batch_{b['batch_id']}"
                )])
        else:
            buttons.append([InlineKeyboardButton("📝 No batches", callback_data="none")])
        
        buttons.append([InlineKeyboardButton("➕ Add Batch", callback_data="add_batch")])
        buttons.append([InlineKeyboardButton("➖ Remove Another", callback_data="remove_batch")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_start")])
        
        kb = InlineKeyboardMarkup(buttons)
        
        await safe_edit(
            success_msg,
            "🤖 **AUTO MODE**\n\n"
            "📦 Your Batches:\n\n"
            "✅ = Active | ⏸️ = Paused\n\n"
            "✨ Batch removed!\n\n"
            "Select batch:",
            reply_markup=kb
        )
        
    except ValueError:
        await safe_reply(message, "❌ Send a number like `1` or `2`")
    except Exception as e:
        logger.error(f"Remove error: {e}", exc_info=True)
        await safe_reply(message, f"❌ Error: {str(e)[:100]}")

async def handle_set_time(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle set time"""
    user_id = callback.from_user.id
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'set_time',
        'batch_id': batch_id,
        'step': 'waiting_time'
    })
    
    await safe_edit(
        callback.message,
        "⏰ **SET TIME (IST)**\n\n"
        "Send time:\n"
        "`09:00 AM`\n"
        "`02:30 PM`\n\n"
        "Or /cancel"
    )

async def handle_time_input(client: Client, message: Message, batch_id: str, time_str: str, batch_manager):
    """Handle time input"""
    user_id = message.from_user.id
    
    parsed = format_indian_time(time_str)
    
    if not parsed:
        await safe_reply(message, "❌ Invalid format! Use: `09:00 AM`")
        return
    
    await db.update_batch_setting(batch_id, 'schedule_time', parsed)
    
    batch = await db.get_batch(batch_id)
    
    if batch_manager and batch and batch['is_active']:
        try:
            await batch_manager.schedule_batch(batch_id, parsed)
            await safe_reply(
                message,
                f"✅ **Time Set & Scheduled!**\n\n"
                f"⏰ Daily at {time_str} IST"
            )
        except Exception as e:
            logger.error(f"Schedule error: {e}")
            await safe_reply(message, f"✅ Time set to {time_str} IST")
    else:
        await safe_reply(message, f"✅ Time set to {time_str} IST\n\n💡 Activate batch to schedule")
    
    await db.clear_user_session(user_id)

async def handle_set_chat(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle set chat"""
    user_id = callback.from_user.id
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'set_chat',
        'batch_id': batch_id,
        'step': 'waiting_chat'
    })
    
    await safe_edit(
        callback.message,
        "🎯 **SET DESTINATION**\n\n"
        "Send channel ID:\n"
        "`-1001234567890`\n\n"
        "💡 Use /id in channel\n\n"
        "Or /cancel"
    )

async def handle_chat_input(client: Client, message: Message, batch_id: str, chat_str: str):
    """
    ✅ FIXED: Simple save - NO VERIFICATION
    """
    user_id = message.from_user.id
    
    channel_id = extract_channel_id(chat_str)
    
    if not channel_id:
        await safe_reply(
            message,
            "❌ **Invalid Channel ID!**\n\n"
            "Use format: `-1001234567890`\n\n"
            "Get ID by:\n"
            "1. Add bot to channel as admin\n"
            "2. Send /id in channel\n"
            "3. Copy the ID"
        )
        return
    
    # ✅ SIMPLE SAVE - NO VERIFICATION
    await db.update_batch_setting(batch_id, 'destination_id', int(channel_id))
    
    await safe_reply(
        message,
        f"✅ **Destination Set!**\n\n"
        f"🎯 `{channel_id}`\n\n"
        f"⚠️ **Important:**\n"
        f"• Make bot admin in channel\n"
        f"• Grant 'Post Messages' permission\n\n"
        f"💡 Bot will verify access when sending"
    )
    
    await db.clear_user_session(user_id)

async def handle_set_quality(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle set quality"""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("480p", callback_data=f"bquality_{batch_id}_480p")],
        [InlineKeyboardButton("720p", callback_data=f"bquality_{batch_id}_720p")],
        [InlineKeyboardButton("1080p", callback_data=f"bquality_{batch_id}_1080p")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"batch_{batch_id}")]
    ])
    
    await safe_edit(callback.message, "🎬 **SELECT QUALITY**", reply_markup=kb)

async def handle_quality_set(client: Client, callback: CallbackQuery, batch_id: str, quality: str):
    """Handle quality set"""
    await db.update_batch_setting(batch_id, 'quality', quality)
    await safe_answer(callback, f"✅ Quality: {quality}", show_alert=True)
    await show_batch_settings(client, callback, batch_id)

async def handle_refresh(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle refresh"""
    if not _batch_manager:
        await safe_answer(callback, "❌ Error!", show_alert=True)
        return
    
    await safe_answer(callback, "🔄 Processing...", show_alert=False)
    
    status = await safe_reply(callback.message, "🔄 **Processing...**")
    
    result = await _batch_manager.process_batch(
        batch_id,
        force_refresh=False,
        progress_chat=callback.message.chat.id
    )
    
    if result['success']:
        await safe_edit(
            status,
            f"✅ **Complete!**\n\n"
            f"📤 Sent: {result.get('sent', 0)}\n"
            f"❌ Failed: {result.get('failed', 0)}\n"
            f"📦 Total: {result.get('total', 0)}"
        )
    else:
        error = result.get('error', 'Unknown')
        details = result.get('details', '')
        await safe_edit(status, f"❌ **{error}**\n\n{details}")

async def handle_backup(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle backup"""
    if not _batch_manager:
        await safe_answer(callback, "❌ Error!", show_alert=True)
        return
    
    await safe_answer(callback, "💾 Generating...", show_alert=False)
    
    try:
        backup_json = await _batch_manager.get_backup_data(batch_id)
        
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(backup_json)
            temp_path = f.name
        
        batch = await db.get_batch(batch_id)
        filename = f"{batch['batch_name']}_backup.json"
        
        await callback.message.reply_document(
            document=temp_path,
            caption=f"💾 **Backup**\n\n📦 {batch['batch_name']}",
            file_name=filename
        )
        
        import os
        os.remove(temp_path)
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await safe_reply(callback.message, f"❌ Failed: {str(e)[:100]}")

async def handle_restore(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle restore"""
    user_id = callback.from_user.id
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'restore',
        'batch_id': batch_id,
        'step': 'waiting_file'
    })
    
    await safe_edit(
        callback.message,
        "📥 **RESTORE FROM BACKUP**\n\n"
        "Send backup JSON file\n\n"
        "💡 Will sync all sent content + settings\n\n"
        "Or /cancel"
    )

async def handle_restore_file(client: Client, message: Message, batch_id: str):
    """Process restore file"""
    user_id = message.from_user.id
    
    if not message.document or not message.document.file_name.endswith('.json'):
        await safe_reply(message, "❌ Send a valid JSON backup file!")
        return
    
    status = await safe_reply(message, "📥 Restoring...")
    
    try:
        file_path = await message.download()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            backup_json = f.read()
        
        result = await _batch_manager.restore_backup(backup_json, batch_id)
        
        import os
        os.remove(file_path)
        
        await db.clear_user_session(user_id)
        
        if result['success']:
            await safe_edit(status, result.get('message', '✅ Restored!'))
        else:
            await safe_edit(status, f"❌ **Restore Failed**\n\n{result.get('error', 'Unknown')}")
            
    except Exception as e:
        logger.error(f"Restore error: {e}", exc_info=True)
        await safe_edit(status, f"❌ Error: {str(e)[:100]}")
        await db.clear_user_session(user_id)

async def handle_set_caption(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle set caption"""
    user_id = callback.from_user.id
    
    await db.save_user_session(user_id, 'auto', {
        'action': 'set_caption',
        'batch_id': batch_id,
        'step': 'waiting_caption'
    })
    
    await safe_edit(
        callback.message,
        "📝 **SET CAPTION**\n\n"
        "Send caption text\n\n"
        "Or /cancel"
    )

async def handle_caption_input(client: Client, message: Message, batch_id: str, caption: str):
    """Handle caption input"""
    user_id = message.from_user.id
    
    await db.update_batch_setting(batch_id, 'custom_caption', caption)
    await safe_reply(message, f"✅ **Caption Set!**\n\n{caption[:100]}...")
    await db.clear_user_session(user_id)

async def handle_set_style(client: Client, callback: CallbackQuery, batch_id: str):
    """Handle set style"""
    buttons = []
    
    for key, style in CAPTION_STYLES.items():
        buttons.append([InlineKeyboardButton(
            style['name'],
            callback_data=f"bstyle_{batch_id}_{key}"
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"batch_{batch_id}")])
    
    kb = InlineKeyboardMarkup(buttons)
    await safe_edit(callback.message, "🎨 **SELECT STYLE**", reply_markup=kb)

async def handle_style_set(client: Client, callback: CallbackQuery, batch_id: str, style: str):
    """Handle style set"""
    await db.update_batch_setting(batch_id, 'caption_style', style)
    await safe_answer(callback, f"✅ Style: {CAPTION_STYLES[style]['name']}", show_alert=True)
    await show_batch_settings(client, callback, batch_id)

async def handle_toggle_batch(client: Client, callback: CallbackQuery, batch_id: str):
    """Toggle batch"""
    batch = await db.get_batch(batch_id)
    
    new_status = 0 if batch['is_active'] else 1
    await db.update_batch_setting(batch_id, 'is_active', new_status)
    
    if new_status:
        if batch['schedule_time'] and _batch_manager:
            try:
                await _batch_manager.schedule_batch(batch_id, batch['schedule_time'])
                await safe_answer(callback, "✅ Activated & scheduled!", show_alert=True)
            except:
                await safe_answer(callback, "✅ Activated!", show_alert=True)
        else:
            await safe_answer(callback, "✅ Activated!", show_alert=True)
    else:
        if _batch_manager:
            _batch_manager.stop_batch(batch_id)
        await safe_answer(callback, "⏸️ Paused!", show_alert=True)
    
    await show_batch_settings(client, callback, batch_id)

async def handle_get_id(client: Client, message: Message):
    """Get chat ID"""
    await safe_reply(
        message,
        f"🆔 **CHAT ID**\n\n"
        f"`{message.chat.id}`\n\n"
        f"Copy to set as destination"
    )

async def handle_reset_ask(client: Client, callback: CallbackQuery, batch_id: str):
    """Ask for reset confirmation"""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Reset Batch", callback_data=f"reset_{batch_id}_confirm")],
        [InlineKeyboardButton("❌ No, Cancel", callback_data=f"batch_{batch_id}")]
    ])

    await safe_edit(
        callback.message,
        "⚠️ **CONFIRM RESET?**\n\n"
        "This will:\n"
        "• Clear all sent content history\n"
        "• Reset progress to 0%\n"
        "• Allow fresh start for this batch\n\n"
        "**Settings (Quality, Chat, etc) will remain.**\n\n"
        "Are you sure?",
        reply_markup=kb
    )

async def handle_reset_confirm(client: Client, callback: CallbackQuery, batch_id: str):
    """Confirm reset"""
    if await db.reset_batch_progress(batch_id):
        await safe_answer(callback, "✅ Batch reset successfully!", show_alert=True)
        await show_batch_settings(client, callback, batch_id)
    else:
        await safe_answer(callback, "❌ Failed to reset!", show_alert=True)
