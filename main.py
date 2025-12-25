import logging
import asyncio
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import *
from database import db
from api_client import api_client
from batch_manager import BatchManager
from utils import safe_reply, safe_edit, safe_answer
from backup_manager import backup_loop
import manual_mode
import auto_mode

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Initialize client
app = Client(
    "dual_mode_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=MAX_WORKERS
)

# Global batch manager
batch_manager_instance = None

# Web server
web_app = web.Application()

async def health_check(request):
    return web.Response(text="✅ Dual Mode Bot Running!")

web_app.router.add_get("/", health_check)
web_app.router.add_get("/health", health_check)

# === COMMANDS ===
@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Manual Mode", callback_data="mode_manual")],
        [InlineKeyboardButton("🤖 Auto Mode", callback_data="mode_auto")]
    ])
    
    await safe_reply(
        message,
        "🚀 **DUAL MODE BOT**\n\n"
        "Choose mode:\n\n"
        "📝 **Manual**: Upload TXT file\n"
        "🤖 **Auto**: Batch scheduling\n\n"
        "Select mode:",
        reply_markup=kb
    )

@app.on_message(filters.command("cancel"))
async def cancel_handler(client: Client, message: Message):
    await db.clear_user_session(message.from_user.id)
    await safe_reply(message, "✅ Cancelled! Use /start")

@app.on_message(filters.command("id"))
async def id_handler(client: Client, message: Message):
    await auto_mode.handle_get_id(client, message)

@app.on_message(filters.command("stop"))
async def stop_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in manual_mode.active_downloads:
        manual_mode.active_downloads[user_id]['running'] = False
        await safe_reply(message, "⛔ Stopped!")
    else:
        await safe_reply(message, "💤 No active downloads")

# === MODE SELECTION ===
@app.on_callback_query(filters.regex(r"^mode_"))
async def mode_selection(client: Client, callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if mode == "manual":
        await manual_mode.start_manual_mode(client, callback.message)
    elif mode == "auto":
        await auto_mode.start_auto_mode(client, callback.message, user_id)

# === BACK BUTTONS ===
@app.on_callback_query(filters.regex(r"^back_to_"))
async def back_handler(client: Client, callback: CallbackQuery):
    dest = callback.data.split("back_to_")[1]
    user_id = callback.from_user.id
    
    if dest == "start":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Manual Mode", callback_data="mode_manual")],
            [InlineKeyboardButton("🤖 Auto Mode", callback_data="mode_auto")]
        ])
        
        await safe_edit(
            callback.message,
            "🚀 **DUAL MODE BOT**\n\n"
            "Choose mode:\n\n"
            "📝 **Manual**: Upload TXT file\n"
            "🤖 **Auto**: Batch scheduling\n\n"
            "Select mode:",
            reply_markup=kb
        )
    elif dest == "auto":
        await auto_mode.start_auto_mode(client, callback.message, user_id)

# === MANUAL MODE ===
@app.on_message(filters.document & filters.private)
async def document_handler(client: Client, message: Message):
    """✅ IMPROVED: Handle both TXT files and restore JSON files"""
    user_id = message.from_user.id
    filename = message.document.file_name
    
    # Check if user is in restore mode
    session = await db.get_user_session(user_id)
    
    if session and session['mode'] == 'auto':
        action = session['data'].get('action')
        
        # ✅ Handle restore file
        if action == 'restore' and filename.endswith('.json'):
            batch_id = session['data'].get('batch_id')
            await auto_mode.handle_restore_file(client, message, batch_id)
            return
    
    # Handle manual mode TXT file
    if filename.endswith('.txt'):
        await manual_mode.handle_txt_file(client, message)

@app.on_callback_query(filters.regex(r"^manual_"))
async def manual_callbacks(client: Client, callback: CallbackQuery):
    await manual_mode.handle_range_selection(client, callback)

@app.on_callback_query(filters.regex(r"^quality_"))
async def quality_callbacks(client: Client, callback: CallbackQuery):
    await manual_mode.handle_quality_selection(client, callback)

@app.on_callback_query(filters.regex(r"^stop_download$"))
async def stop_download_cb(client: Client, callback: CallbackQuery):
    await manual_mode.stop_download(client, callback)

# === AUTO MODE ===
@app.on_callback_query(filters.regex(r"^batch_"))
async def batch_callback(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("batch_")[1]
    await auto_mode.show_batch_settings(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^add_batch$"))
async def add_batch_cb(client: Client, callback: CallbackQuery):
    await auto_mode.handle_add_batch(client, callback)

@app.on_callback_query(filters.regex(r"^remove_batch$"))
async def remove_batch_cb(client: Client, callback: CallbackQuery):
    await auto_mode.handle_remove_batch(client, callback)

@app.on_callback_query(filters.regex(r"^settime_"))
async def settime_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_set_time(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^setchat_"))
async def setchat_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_set_chat(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^setquality_"))
async def setquality_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_set_quality(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^bquality_"))
async def bquality_cb(client: Client, callback: CallbackQuery):
    parts = callback.data.split("_")
    batch_id = parts[1]
    quality = parts[2]
    await auto_mode.handle_quality_set(client, callback, batch_id, quality)

@app.on_callback_query(filters.regex(r"^refresh_"))
async def refresh_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_refresh(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^backup_"))
async def backup_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_backup(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^restore_"))  # ✅ NEW
async def restore_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_restore(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^reset_"))
async def reset_cb(client: Client, callback: CallbackQuery):
    data = callback.data.split("_")
    batch_id = data[1]

    if len(data) == 3 and data[2] == "confirm":
        await auto_mode.handle_reset_confirm(client, callback, batch_id)
    else:
        await auto_mode.handle_reset_ask(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^setcaption_"))
async def setcaption_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_set_caption(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^setstyle_"))
async def setstyle_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_set_style(client, callback, batch_id)

@app.on_callback_query(filters.regex(r"^bstyle_"))
async def bstyle_cb(client: Client, callback: CallbackQuery):
    parts = callback.data.split("_")
    batch_id = parts[1]
    style = parts[2]
    await auto_mode.handle_style_set(client, callback, batch_id, style)

@app.on_callback_query(filters.regex(r"^toggle_"))
async def toggle_cb(client: Client, callback: CallbackQuery):
    batch_id = callback.data.split("_")[1]
    await auto_mode.handle_toggle_batch(client, callback, batch_id)

# === TEXT INPUT ===
@app.on_message(filters.text & filters.private & ~filters.command(["start", "cancel", "id", "stop"]))
async def text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = await db.get_user_session(user_id)
    
    if not session:
        return
    
    mode = session['mode']
    data = session['data']
    action = data.get('action', '')
    
    # Manual mode
    if mode == 'manual' and data.get('step') == 'range_input':
        await manual_mode.handle_range_input(client, message)
    
    # Auto mode
    elif mode == 'auto':
        if action == 'add_batch' and data.get('step') == 'waiting_batch_id':
            await auto_mode.handle_batch_id_input(
                client, message, message.text.strip(), batch_manager_instance
            )
        
        elif action == 'remove_batch' and data.get('step') == 'select_batch':
            await auto_mode.handle_remove_batch_input(client, message, message.text.strip())
        
        elif action == 'set_time' and data.get('step') == 'waiting_time':
            await auto_mode.handle_time_input(
                client, message, data['batch_id'], message.text.strip(), batch_manager_instance
            )
        
        elif action == 'set_chat' and data.get('step') == 'waiting_chat':
            await auto_mode.handle_chat_input(client, message, data['batch_id'], message.text.strip())
        
        elif action == 'set_caption' and data.get('step') == 'waiting_caption':
            await auto_mode.handle_caption_input(client, message, data['batch_id'], message.text.strip())

# === MAIN ===
async def main():
    global batch_manager_instance
    
    try:
        # Initialize database
        logger.info("🔧 Initializing database...")
        await db.init_db()
        
        # Initialize batch manager
        logger.info("🔧 Initializing batch manager...")
        batch_manager_instance = BatchManager(app)
        auto_mode.set_batch_manager(batch_manager_instance)
        
        # Start web server
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"✅ Web server on port {PORT}")
        
        # Start bot
        logger.info("🤖 Starting bot...")
        await app.start()
        
        me = await app.get_me()
        logger.info("=" * 70)
        logger.info(f"🤖 Bot: @{me.username}")
        logger.info(f"🆔 ID: {me.id}")
        logger.info("=" * 70)
        
        # Load scheduled batches
        logger.info("📅 Loading schedules...")
        await batch_manager_instance.load_all_scheduled_batches()
        
        # Start backup loop
        asyncio.create_task(backup_loop(app, batch_manager_instance))

        logger.info("🚀 BOT STARTED!")
        logger.info("=" * 70)
        logger.info("✨ NEW FEATURES:")
        logger.info("   • ✅ Restore button - Sync from backup")
        logger.info("   • ✅ Scheduled progress - Real-time updates")
        logger.info("   • ✅ Completion message - Shows update timestamp")
        logger.info("   • ✅ User ID fix - No more bot/user confusion")
        logger.info("   • ✅ Auto Backup - Every 30 mins")
        logger.info("   • ✅ FloodWait Fix - Smooth buttons")
        logger.info("=" * 70)
        
        # Keep running
        await idle()
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}", exc_info=True)
        raise
    finally:
        try:
            await app.stop()
            await api_client.close()
        except:
            pass

if __name__ == "__main__":
    logger.info("🚀 Starting bot...")
    
    try:
        from pyrogram import idle
        app.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal: {e}", exc_info=True)
