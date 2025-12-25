# 🚀 Dual Mode Telegram Bot - ADVANCED EDITION

Production-ready Telegram bot with two powerful modes and SUPER ADVANCED features!

## ✨ NEW ADVANCED FEATURES

### 🧠 Smart Refresh
- **Intelligent Diff**: Compares database, channel, and server content
- **Only New Content**: Never re-uploads old content
- **Hash-based Tracking**: Prevents duplicates even with URL changes
- **Memory Efficient**: Tracks only what's necessary

### ⏸️ Stop & Resume
- **Graceful Stop**: Press stop anytime, state is saved
- **Resume from Pause**: Continue exactly where you left off
- **State Synchronization**: Database tracks every upload
- **No Data Loss**: All progress is preserved

### 💾 Backup & Restore
- **Complete Backup**: Download full batch history as JSON
- **Easy Restore**: Upload backup file to restore progress
- **Includes Everything**: Sent content, state, history, settings
- **Cross-Session**: Backup survives bot restarts

### 🌏 Indian Timezone (IST)
- **Proper IST Support**: Set times in 12-hour format with AM/PM
- **Accurate Scheduling**: Converts IST to UTC correctly
- **No Confusion**: Always shows "IST" in confirmations
- **Examples**: 09:00 AM, 02:30 PM, 11:45 PM

### 🎨 Enhanced Thumbnail Generation
- **Heroku Compatible**: Multiple fallback methods
- **Smart Seek**: Chooses best frame based on duration
- **5 Methods**: Tries 5 different techniques until success
- **Always Works**: Generates thumbnails even in restricted environments

### 🔐 Channel Verification
- **Pre-Upload Check**: Verifies bot has access before uploading
- **Admin Check**: Ensures bot has required permissions
- **Clear Errors**: Shows exactly what's wrong
- **No Failed Uploads**: Catches issues before they happen

## 📋 Original Features

### 📝 Manual Mode
- Upload TXT file with links
- Select range or process all
- Quality selection (480p/720p/1080p original)
- Real-time progress tracking
- Support for all file types (video, image, document)
- Auto-split for 2GB+ files
- Failed link handling (YouTube, MPD)

### 🤖 Auto Mode
- Add multiple batches by ID
- Schedule daily auto-updates
- Set destination channel/group
- Custom captions and styles
- 10 preset caption styles
- Smart duplicate detection

## 🎯 Supported Links

- **Videos**: M3U8, HLS, MP4, MKV, AVI, and more
- **Images**: JPG, PNG, GIF, WebP
- **Documents**: PDF, DOC, ZIP, RAR
- **Streaming**: M3U8, HLS (direct)

**Note**: YouTube and MPD links send manual download message.

## 🛠️ Setup

### Prerequisites
- Python 3.11+
- FFmpeg (auto-installed in Docker/Heroku)
- Telegram Bot Token
- API_ID and API_HASH from my.telegram.org

### Environment Variables

```bash
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
PORT=10000
```

### Local Installation

```bash
# Clone repository
git clone <repo-url>
cd dual-mode-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (Linux)
sudo apt-get install ffmpeg ffprobe libavcodec-extra

# Set environment variables
export API_ID="your_api_id"
export API_HASH="your_api_hash"
export BOT_TOKEN="your_bot_token"

# Run bot
python main.py
```

### Docker Deployment

```bash
# Build image (includes FFmpeg)
docker build -t dual-mode-bot .

# Run container
docker run -d \
  --name dual-bot \
  -e API_ID="your_api_id" \
  -e API_HASH="your_api_hash" \
  -e BOT_TOKEN="your_bot_token" \
  -p 10000:10000 \
  --restart unless-stopped \
  dual-mode-bot
```

### Heroku Deployment

1. **Fork this repository**

2. **Create Heroku app:**
   ```bash
   heroku create your-app-name
   ```

3. **Set Config Vars:**
   - Go to Settings → Config Vars
   - Add: API_ID, API_HASH, BOT_TOKEN

4. **Deploy:**
   ```bash
   git push heroku main
   ```

5. **FFmpeg is auto-installed via Dockerfile!**

## 📖 Usage Guide

### Auto Mode - COMPLETE WORKFLOW

#### 1. Add Batch
```
/start → Auto Mode → Add Batch
→ Send 24-character batch ID
→ Bot fetches and saves batch
```

#### 2. Configure Batch
```
Click on batch name
→ Set Chat: Send channel ID (bot will verify access)
→ Set Quality: 480p/720p/1080p
→ Set Time: 09:00 AM (IST format)
→ Set Caption: Custom footer text (optional)
→ Cap Style: Choose from 10 presets
```

#### 3. Activate & Schedule
```
Click "Activate" button
→ Bot enables auto-updates
→ Schedule activates automatically
→ Bot will process daily at set time
```

#### 4. First Upload
```
Click "Refresh" to upload all content
→ Bot fetches from server
→ Compares with database
→ Uploads only new items
→ Saves progress
```

#### 5. Daily Auto-Updates
```
Bot runs automatically at scheduled time (IST)
→ Fetches latest content from server
→ Smart diff: Only uploads NEW items
→ Never re-uploads old content
→ State saved after each item
```

#### 6. Stop & Resume
```
During processing, click "Pause"
→ Bot stops gracefully after current item
→ State saved: knows exactly where it stopped
→ Click "Resume" anytime to continue
→ Picks up exactly where it left off
```

#### 7. Backup & Restore
```
Get Backup:
→ Click "Get Backup" button
→ Bot sends JSON file with complete history
→ Save this file safely

Restore:
→ Click "Restore" button
→ Send previously saved JSON file
→ Bot restores all progress
→ Continues as if nothing happened
```

### Manual Mode Usage

1. `/start` → Select **Manual Mode**
2. Upload TXT file with format:
   ```
   Title 1: https://example.com/video.m3u8
   Title 2: https://example.com/image.jpg
   Title 3: https://example.com/doc.pdf
   ```
3. Select range or full
4. Choose quality
5. Bot downloads and uploads automatically

## 🎨 Caption Styles

10 preset styles available:
1. **Normal** - Simple title only
2. **Elegant** - ✨ Title ✨
3. **Minimal** - ▸ Title
4. **Boxed** - Title in box border
5. **Professional** - 📚 Title with line
6. **Modern** - ⚡ Title with premium badge
7. **Classic** - 📖 Title educational
8. **Bold** - 🔥 Title with quality badge
9. **Premium** - 💫 Title luxury edition
10. **Tech** - ⚙️ Title technical

## 🔥 Advanced Features Explained

### Smart Refresh Algorithm
```
1. Fetch latest content from server (API call)
2. Parse all items (titles, URLs, types)
3. Get sent history from database (hash-based)
4. Calculate diff: new_items = server_items - sent_items
5. Process only new items
6. Mark each as sent after successful upload
```

### Resume Mechanism
```
Stop pressed:
1. Current item finishes uploading
2. Save: current_index, success_count, failed_count
3. Mark batch as "paused"
4. Exit gracefully

Resume pressed:
1. Load saved state from database
2. Fetch latest content from server
3. Start from saved current_index
4. Continue processing
5. Mark as "active" when done
```

### Backup Structure
```json
{
  "batch": {
    "batch_id": "...",
    "batch_name": "...",
    "settings": {...}
  },
  "sent_content": [
    {
      "title": "...",
      "url": "...",
      "hash": "...",
      "type": "video",
      "sent_at": "...",
      "message_id": 123
    }
  ],
  "state": {
    "current_index": 50,
    "total_items": 100,
    "success": 48,
    "failed": 2
  },
  "history": [...]
}
```

### IST Time Conversion
```
User enters: 09:00 AM
Bot converts: 09:00 (24-hour)
Bot stores: "09:00" in IST
Scheduler uses: pytz IST timezone
Converts to UTC: 03:30 (UTC)
Sleeps until: 03:30 UTC = 09:00 IST
```

## 🔧 Troubleshooting

### Bot not starting?
- Check all environment variables are set
- Verify bot token is valid
- Ensure Python 3.11+ is installed

### FFmpeg not working?
- **Docker/Heroku**: Auto-installed via Dockerfile
- **Local**: Install manually: `sudo apt-get install ffmpeg`
- **Verification**: Run `ffmpeg -version` in terminal

### Thumbnails not generating?
- Bot tries 5 different methods automatically
- Works even without FFmpeg (skips thumbnails)
- Check logs for specific error

### Time schedule wrong?
- Always use IST format: 09:00 AM, not 9:00
- Bot shows "IST" in confirmation
- Check logs for actual scheduled time

### Auto mode not working?
- Ensure batch ID is exactly 24 characters
- Check destination channel permissions
- Bot must be admin with "Post Messages" right
- Use "Set Chat" to verify access

### Smart refresh uploading duplicates?
- Should never happen with hash-based tracking
- If it does: Check logs for hash collisions
- Use "Get Backup" to see sent history

### Resume not working?
- Make sure you clicked "Pause", not "Stop"
- "Stop" clears state, "Pause" preserves it
- Check batch status shows ⏸️ icon

### Backup file too large?
- Normal for large batches (thousands of items)
- Compress JSON file if needed
- Split backup not supported yet

## 📊 Performance Tips

1. **For best results:**
   - Use 720p for balance of quality and speed
   - Set destination to avoid manual forwarding
   - Schedule during low-traffic hours (2-5 AM IST)

2. **For large batches (1000+ items):**
   - Use "Refresh" in multiple sessions
   - Pause every 200-300 items
   - Take backup regularly
   - Monitor bot logs

3. **For reliability:**
   - Keep bot running 24/7 (Heroku/Docker)
   - Take weekly backups
   - Test destination channel access first
   - Use high-quality VPS/server

## 🚀 Deployment Checklist

- [ ] Environment variables set (API_ID, API_HASH, BOT_TOKEN)
- [ ] FFmpeg installed/verified
- [ ] Bot tested locally first
- [ ] Destination channels configured
- [ ] Bot added as admin in all channels
- [ ] Test batch added and configured
- [ ] First manual refresh successful
- [ ] Schedule set and verified (check logs)
- [ ] Backup taken and tested
- [ ] Bot running in background/Docker/Heroku

## 📝 Database Schema

```sql
-- Enhanced tracking tables
batches (batch_id, batch_name, user_id, destination_id, 
         quality, schedule_time, custom_caption, caption_style,
         is_active, is_paused, total_processed, ...)

sent_content (id, batch_id, destination_id, content_title,
              content_url, content_hash, file_type, 
              sent_at, message_id)

batch_state (batch_id, current_index, total_items,
             items_processed, items_success, items_failed,
             last_item_url, updated_at)

processing_history (id, batch_id, action, details, timestamp)
```

## 🎉 Credits

Built with:
- Pyrogram (Telegram MTProto API)
- yt-dlp (Video downloads)
- FFmpeg (Video processing)
- aiohttp (Async HTTP)
- aiosqlite (Database)
- pytz (Timezone support)

---

**🔥 Production-ready, feature-complete, battle-tested, and SUPER ADVANCED! 🔥**

## 🆘 Support

For issues:
1. Check logs: `bot.log`
2. Verify configuration
3. Test with simple file first
4. Check database: `bot_data.db`
5. Review this README for solutions

## 📜 Version History

### v2.0 - Advanced Edition (Current)
- ✅ Smart refresh (only new content)
- ✅ Stop & resume functionality
- ✅ Backup & restore
- ✅ IST timezone support
- ✅ Channel verification
- ✅ State synchronization
- ✅ Enhanced thumbnail generation
- ✅ Hash-based duplicate prevention
- ✅ Complete processing history

### v1.0 - Initial Release
- Basic manual mode
- Basic auto mode
- Simple scheduling

---

**Made with ❤️ for advanced automation**
