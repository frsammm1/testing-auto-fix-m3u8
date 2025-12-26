import asyncio
import logging
import json
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, ChannelPrivate
from typing import Optional, Dict, List
from database import db
from api_client import api_client
from utils import parse_auto_content, is_failed_url, sanitize_filename, is_youtube_url, is_mpd_url, safe_send, safe_edit, safe_reply
from caption_styles import apply_caption_style
from downloader import download_video, download_image, download_document
from uploader import upload_video, upload_photo, upload_document, send_failed_link
from video_processor import finalize_video, validate_video, get_video_duration, get_video_dimensions, generate_thumbnail
from config import DOWNLOAD_DIR
from url_helper import process_url, is_youtube_url, is_mpd_url
import os
import pytz

logger = logging.getLogger(__name__)

class BatchManager:
    def __init__(self, client: Client):
        self.client = client
        self.active_tasks = {}
        self.active_downloads = {}
        self.stop_gracefully = {}
        logger.info("✅ BatchManager initialized")
    
    async def add_batch(self, batch_id: str, user_id: int) -> Optional[Dict]:
        """✅ Add batch - CLEAN"""
        try:
            logger.info(f"📦 Adding batch {batch_id} for user {user_id}")
            
            # Fetch from API
            content, batch_name = await api_client.get_batch_content(batch_id)
            
            if not content or not batch_name:
                logger.error("❌ API fetch failed")
                return None
            
            logger.info(f"✅ Fetched: {batch_name}")
            
            # Save to database
            success = await db.add_batch(batch_id, batch_name, user_id)
            
            if not success:
                logger.error("❌ Database save failed")
                return None
            
            logger.info(f"✅ Saved successfully")
            
            return {
                'batch_id': batch_id,
                'batch_name': batch_name
            }
            
        except Exception as e:
            logger.error(f"❌ Add batch error: {e}", exc_info=True)
            return None
    
    async def get_smart_content_diff(self, batch_id: str, server_items: List[Dict]) -> List[Dict]:
        """
        ✅ ENHANCED: Get NEW content + RETRY failed content
        """
        logger.info(f"🧠 Smart diff for {len(server_items)} items")
        
        sent_urls = set()
        failed_urls = []
        
        async with db.get_connection() as conn:
            # Get successfully sent
            async with conn.execute(
                "SELECT content_url FROM sent_content WHERE batch_id = ? AND status = 'success'",
                (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                sent_urls = {row[0] for row in rows}
            
            # Get failed URLs for retry
            async with conn.execute(
                "SELECT content_url FROM sent_content WHERE batch_id = ? AND status = 'failed'",
                (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    url = row[0]
                    # Don't retry YouTube/MPD as they will fail again
                    if not is_youtube_url(url) and not is_mpd_url(url):
                        failed_urls.append(url)
        
        logger.info(f"📊 {len(sent_urls)} sent, {len(failed_urls)} to retry")
        
        new_items = [item for item in server_items if item['url'] not in sent_urls]
        retry_items = [item for item in server_items if item['url'] in failed_urls]
        
        items_to_process = retry_items + new_items
        
        logger.info(f"🆕 {len(new_items)} new, {len(retry_items)} retry = {len(items_to_process)} total")
        return items_to_process
    
    async def process_batch(
        self,
        batch_id: str,
        force_refresh: bool = False,
        resume: bool = False,
        progress_chat: Optional[int] = None,
        start_time: Optional[datetime] = None
    ) -> Dict:
        """
        ✅ FIXED: Simple direct send - NO VERIFICATION
        """
        try:
            logger.info(f"🔄 Processing {batch_id}")
            
            if start_time is None:
                start_time = datetime.now()
            
            # Get batch
            batch = await db.get_batch(batch_id)
            if not batch or not batch['destination_id']:
                return {'success': False, 'error': 'Invalid batch or destination not set'}
            
            destination = batch['destination_id']
            batch_name = batch['batch_name']
            
            logger.info(f"🎯 Destination: {destination}")
            
            # Fetch content
            content, _ = await api_client.get_batch_content(batch_id)
            if not content:
                return {'success': False, 'error': 'Fetch failed'}
            
            # Parse items
            all_items = parse_auto_content(content)
            if not all_items:
                return {'success': False, 'error': 'No links'}
            
            logger.info(f"📊 Server: {len(all_items)} items")
            
            # Get items to process
            if force_refresh:
                items_to_process = all_items
            else:
                items_to_process = await self.get_smart_content_diff(batch_id, all_items)
            
            if not items_to_process:
                return {
                    'success': True,
                    'sent': 0,
                    'message': 'All up to date ✅'
                }
            
            logger.info(f"🆕 Processing {len(items_to_process)} items")
            
            # Setup tracking
            download_key = f"{batch_id}_{datetime.now().timestamp()}"
            self.active_downloads[download_key] = {'running': True, 'batch_id': batch_id}
            self.stop_gracefully[download_key] = False
            
            # Process
            success = 0
            failed = 0
            
            quality = batch['quality'] or '720p'
            caption_style = batch['caption_style'] or 'normal'
            custom_caption = batch['custom_caption'] or ''
            
            for idx, item in enumerate(items_to_process, 1):
                # Check stop
                if self.stop_gracefully.get(download_key, False):
                    logger.info(f"⏸️ Graceful stop requested")
                
                if not self.active_downloads[download_key]['running']:
                    logger.info("⛔ Stopped")
                    break
                
                # Progress
                prog = None
                if progress_chat:
                    try:
                        prog = await safe_send(
                            self.client,
                            progress_chat,
                            f"📦 **Processing {idx}/{len(items_to_process)}**\n\n"
                            f"📝 {item['title'][:50]}...\n"
                            f"🔄 Starting..."
                        )
                    except:
                        pass
                
                try:
                    # YouTube/MPD handling via url_helper
                    # We check raw url first
                    if is_youtube_url(item['url']) or is_mpd_url(item['url']):
                        await send_failed_link(
                            self.client, destination,
                            item['title'], item['url'], idx, item['type']
                        )
                        # Mark as success? Or failed?
                        # User says: "failed manual link wala msg badhiya tha... unke liye failed manual link..."
                        # So mark as 'success' so it doesn't retry?
                        # Or 'failed' so it retries?
                        # If we successfully send the "manual link message", we should probably mark it as 'success'
                        # to avoid spamming the channel with the same manual link message on every refresh.
                        await db.mark_content_sent(batch_id, destination, item['title'], item['url'], 'success')
                        failed += 1 # It technically failed to upload media, but we handled it.
                        if prog:
                            await prog.delete()
                        continue
                    
                    # Download
                    file_path = None
                    download_success = False
                    
                    # STRICT PIPELINE VARIABLES
                    video_duration = 0
                    video_width = 0
                    video_height = 0
                    thumb_path = None

                    if item['type'] == 'video':
                        filename = sanitize_filename(item['title']) + '.mp4'

                        # Note: `download_video` in `downloader.py` internally calls `process_url` from `url_helper.py`.
                        # We don't need to call it here manually unless we need to inspect it.
                        # `downloader.py` handles extraction, headers, yt-dlp options etc.

                        raw_path = await download_video(
                            item['url'], filename, prog,
                            self.active_downloads[download_key],
                            quality=quality
                        )

                        if raw_path and raw_path != 'FAILED':
                            # PIPELINE STEP 1: Finalize (Mandatory)
                            logger.info(f"🎞️ Strict Pipeline: Finalizing {filename}...")
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

                                    # Clean up raw path as we have successful final
                                    if raw_path != final_path:
                                        try:
                                            os.remove(raw_path)
                                        except:
                                            pass
                                else:
                                    logger.warning(f"❌ Validation failed for {filename}. Fallback to Document.")
                                    item['type'] = 'document'
                                    file_path = final_path if os.path.exists(final_path) else raw_path
                            else:
                                logger.warning(f"❌ Finalization failed for {filename}. Fallback to Document.")
                                item['type'] = 'document'
                                file_path = raw_path

                        elif raw_path == 'FAILED':
                            # Should trigger manual link
                            file_path = 'FAILED'

                        download_success = file_path and file_path != 'FAILED'
                    
                    elif item['type'] == 'image':
                        ext = os.path.splitext(item['url'])[1] or '.jpg'
                        filename = sanitize_filename(item['title']) + ext
                        file_path = await download_image(
                            item['url'], filename, prog,
                            self.active_downloads[download_key]
                        )
                        download_success = file_path and file_path != 'FAILED'
                    
                    elif item['type'] == 'document':
                        ext = os.path.splitext(item['url'])[1] or '.pdf'
                        filename = sanitize_filename(item['title']) + ext
                        file_path = await download_document(
                            item['url'], filename, prog,
                            self.active_downloads[download_key]
                        )
                        download_success = file_path and file_path != 'FAILED'
                    
                    if not download_success or not file_path:
                        await send_failed_link(
                            self.client, destination,
                            item['title'], item['url'], idx, item['type']
                        )
                        # Mark as failed in DB immediately to ensure backup consistency
                        await db.mark_content_sent(batch_id, destination, item['title'], item['url'], 'failed')
                        failed += 1
                        if prog:
                            await prog.delete()
                        
                        if self.stop_gracefully.get(download_key, False):
                            logger.info("⏸️ Stop requested, stopping now")
                            self.active_downloads[download_key]['running'] = False
                            break
                        
                        continue
                    
                    # Caption
                    caption = apply_caption_style(
                        item['title'], caption_style, custom_caption
                    )
                    
                    # ✅ UPLOAD
                    upload_success = False
                    
                    try:
                        if item['type'] == 'video':
                            # Pass pre-calculated metadata and thumb
                            upload_success = await upload_video(
                                self.client, destination, file_path, caption, prog,
                                duration=video_duration,
                                width=video_width,
                                height=video_height,
                                thumb_path=thumb_path
                            )
                        elif item['type'] == 'image':
                            upload_success = await upload_photo(
                                self.client, destination, file_path, caption, prog
                            )
                        elif item['type'] == 'document':
                            upload_success = await upload_document(
                                self.client, destination, file_path, caption, prog
                            )
                        
                        if upload_success:
                            success += 1
                            await db.mark_content_sent(batch_id, destination, item['title'], item['url'], 'success')
                            logger.info(f"✅ Item {idx}")
                        else:
                            await db.mark_content_sent(batch_id, destination, item['title'], item['url'], 'failed')
                            failed += 1
                    
                    # ✅ ONLY handle errors when they ACTUALLY occur
                    except ChatAdminRequired:
                        logger.error(f"❌ Not admin in {destination}")
                        return {
                            'success': False,
                            'error': '❌ Bot Not Admin!',
                            'details': 'Make bot admin with Post Messages permission'
                        }
                    
                    except ChannelPrivate:
                        logger.error(f"❌ Channel private")
                        return {
                            'success': False,
                            'error': '❌ Channel Private!',
                            'details': 'Add bot to channel first'
                        }
                    
                    if prog:
                        await prog.delete()
                    
                    if self.stop_gracefully.get(download_key, False):
                        logger.info("⏸️ Stop requested, stopping now")
                        self.active_downloads[download_key]['running'] = False
                        break
                
                except Exception as e:
                    logger.error(f"❌ Item {idx} error: {e}", exc_info=True)
                    await db.mark_content_sent(batch_id, destination, item['title'], item['url'], 'failed')
                    failed += 1
                    if prog:
                        try:
                            await prog.delete()
                        except:
                            pass
                
                await asyncio.sleep(0.5)
            
            # Cleanup
            del self.active_downloads[download_key]
            if download_key in self.stop_gracefully:
                del self.stop_gracefully[download_key]
            
            logger.info(f"📊 Done: {success} success, {failed} failed")
            
            # Send completion message
            if success > 0:
                try:
                    ist = pytz.timezone('Asia/Kolkata')
                    start_time_ist = start_time.astimezone(ist)
                    time_str = start_time_ist.strftime("%d %B %Y, %I:%M %p IST")
                    
                    completion_msg = (
                        f"✅ **UPDATE COMPLETE**\n\n"
                        f"📦 **{batch_name}**\n\n"
                        f"📤 New Items: {success}\n"
                        f"❌ Failed: {failed}\n"
                        f"📊 Total Processed: {success + failed}\n\n"
                        f"🕐 **Updated Till:** {time_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤖 Automated by Dual Mode Bot"
                    )
                    
                    await safe_send(
                        self.client,
                        destination,
                        completion_msg
                    )
                    logger.info("✅ Completion message sent")
                except Exception as e:
                    logger.error(f"❌ Completion message error: {e}")
            
            return {
                'success': True,
                'sent': success,
                'failed': failed,
                'total': len(items_to_process)
            }
            
        except Exception as e:
            logger.error(f"❌ Batch error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def schedule_batch(self, batch_id: str, schedule_time: str):
        """Schedule batch"""
        try:
            # Cancel old
            if batch_id in self.active_tasks:
                old = self.active_tasks[batch_id]
                if not old.done():
                    old.cancel()
                    try:
                        await old
                    except asyncio.CancelledError:
                        pass
                logger.info("⏹️ Cancelled old schedule")
            
            # Create new
            task = asyncio.create_task(self._scheduled_task(batch_id, schedule_time))
            self.active_tasks[batch_id] = task
            logger.info(f"⏰ Scheduled at {schedule_time} IST")
            
        except Exception as e:
            logger.error(f"❌ Schedule error: {e}")
    
    async def _scheduled_task(self, batch_id: str, schedule_time: str):
        """Background task"""
        while True:
            try:
                ist = pytz.timezone('Asia/Kolkata')
                now_ist = datetime.now(ist)
                
                hour, minute = map(int, schedule_time.split(':'))
                target = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if target <= now_ist:
                    target += timedelta(days=1)
                
                wait_seconds = (target - now_ist).total_seconds()
                logger.info(f"⏰ Next run in {wait_seconds/3600:.1f}h")
                
                await asyncio.sleep(wait_seconds)
                
                # Check active
                batch = await db.get_batch(batch_id)
                if not batch or not batch['is_active']:
                    continue
                
                logger.info(f"🔔 Auto-processing {batch_id}")
                
                user_id = batch['user_id']
                start_time = datetime.now()
                
                # Process
                result = await self.process_batch(
                    batch_id, 
                    force_refresh=False,
                    progress_chat=user_id,
                    start_time=start_time
                )
                
                logger.info(f"✅ Auto-processed: {result}")
                
                # Notify user
                try:
                    if result['success']:
                        await safe_send(
                            self.client,
                            user_id,
                            f"✅ **Auto-Update Complete!**\n\n"
                            f"📦 {batch['batch_name']}\n\n"
                            f"📤 Sent: {result.get('sent', 0)}\n"
                            f"❌ Failed: {result.get('failed', 0)}\n"
                            f"📊 Total: {result.get('total', 0)}"
                        )
                except:
                    pass
                
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                logger.info("⏹️ Task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Task error: {e}")
                await asyncio.sleep(3600)
    
    async def get_backup_data(self, batch_id: str) -> str:
        """Get backup with all settings"""
        try:
            batch = await db.get_batch(batch_id)
            
            sent = []
            async with db.get_connection() as conn:
                async with conn.execute(
                    "SELECT content_title, content_url, status, sent_at FROM sent_content WHERE batch_id = ? ORDER BY sent_at",
                    (batch_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        sent.append({
                            'title': row[0],
                            'url': row[1],
                            'status': row[2],
                            'sent_at': row[3]
                        })
            
            backup = {
                'batch': {
                    'batch_id': batch['batch_id'],
                    'batch_name': batch['batch_name'],
                    'user_id': batch['user_id'],
                    'destination_id': batch['destination_id'],
                    'quality': batch['quality'],
                    'schedule_time': batch['schedule_time'],
                    'custom_caption': batch['custom_caption'],
                    'caption_style': batch['caption_style'],
                    'is_active': batch['is_active']
                },
                'sent_content': sent,
                'stats': {
                    'total_sent': len([s for s in sent if s['status'] == 'success']),
                    'total_failed': len([s for s in sent if s['status'] == 'failed']),
                    'backup_time': datetime.now().isoformat()
                },
                'warning': 'DO NOT MODIFY THIS FILE - Generated by Dual Mode Bot'
            }
            
            return json.dumps(backup, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return json.dumps({'error': str(e)})
    
    async def restore_backup(self, backup_json: str, batch_id: str) -> Dict:
        """
        ✅ Restore with settings
        """
        try:
            data = json.loads(backup_json)
            
            if 'batch' not in data or 'sent_content' not in data:
                return {'success': False, 'error': 'Invalid backup file'}
            
            backup_batch_id = data['batch'].get('batch_id')
            
            if backup_batch_id != batch_id:
                return {
                    'success': False, 
                    'error': f'Batch ID mismatch!\n\nBackup: {backup_batch_id}\nCurrent: {batch_id}'
                }
            
            logger.info(f"📥 Restoring {len(data['sent_content'])} items + settings")
            
            # Restore settings
            settings = data['batch']
            restore_settings_success = await db.restore_batch_settings(batch_id, settings)
            
            if not restore_settings_success:
                logger.error("❌ Failed to restore settings")
                return {'success': False, 'error': 'Failed to restore settings'}
            
            logger.info("✅ Settings restored")
            
            # Restore content
            current_batch = await db.get_batch(batch_id)
            if not current_batch:
                return {'success': False, 'error': 'Batch not found'}
            
            destination_id = current_batch['destination_id']
            
            async with db.get_connection() as conn:
                await conn.execute(
                    "DELETE FROM sent_content WHERE batch_id = ?",
                    (batch_id,)
                )
                await conn.commit()
            
            logger.info("🗑️ Cleared existing sent content")
            
            restored_success = 0
            restored_failed = 0
            
            for item in data['sent_content']:
                try:
                    status = item.get('status', 'success')
                    await db.mark_content_sent(
                        batch_id,
                        destination_id,
                        item['title'],
                        item['url'],
                        status
                    )
                    if status == 'success':
                        restored_success += 1
                    else:
                        restored_failed += 1
                except Exception as e:
                    logger.error(f"❌ Restore item error: {e}")
            
            logger.info(f"✅ Restored {restored_success} success + {restored_failed} failed")
            
            reloaded_batch = await db.get_batch(batch_id)
            
            return {
                'success': True,
                'message': (
                    f"✅ **Restore Complete!**\n\n"
                    f"📊 **Settings Loaded:**\n"
                    f"🎯 Destination: {reloaded_batch['destination_id']}\n"
                    f"🎬 Quality: {reloaded_batch['quality']}\n"
                    f"⏰ Schedule: {reloaded_batch['schedule_time']} IST\n"
                    f"📝 Caption: {reloaded_batch['caption_style']}\n\n"
                    f"📦 **Content Synced:**\n"
                    f"✅ Success: {restored_success}\n"
                    f"❌ To Retry: {restored_failed}\n\n"
                    f"💡 Failed items will retry on next update"
                )
            }
            
        except json.JSONDecodeError:
            return {'success': False, 'error': 'Invalid JSON file'}
        except Exception as e:
            logger.error(f"❌ Restore error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)[:100]}
    
    def stop_batch(self, batch_id: str, graceful: bool = True):
        """Stop batch"""
        if batch_id in self.active_tasks:
            self.active_tasks[batch_id].cancel()
            logger.info("⏹️ Stopped scheduled task")
        
        if graceful:
            for key in list(self.active_downloads.keys()):
                if key.startswith(batch_id) or self.active_downloads[key].get('batch_id') == batch_id:
                    self.stop_gracefully[key] = True
                    logger.info(f"⏸️ Graceful stop requested for {key}")
        else:
            for key in list(self.active_downloads.keys()):
                if key.startswith(batch_id) or self.active_downloads[key].get('batch_id') == batch_id:
                    self.active_downloads[key]['running'] = False
    
    async def load_all_scheduled_batches(self):
        """Load schedules on startup"""
        try:
            logger.info("📋 Loading schedules...")
            
            async with db.get_connection() as conn:
                async with conn.execute("""
                    SELECT batch_id, schedule_time, batch_name 
                    FROM batches 
                    WHERE is_active = 1 AND schedule_time IS NOT NULL
                """) as cursor:
                    batches = await cursor.fetchall()
            
            logger.info(f"📦 Found {len(batches)} scheduled")
            
            for batch_id, schedule_time, batch_name in batches:
                logger.info(f"⏰ Scheduling: {batch_name}")
                await self.schedule_batch(batch_id, schedule_time)
            
            logger.info("✅ All loaded!")
            
        except Exception as e:
            logger.error(f"❌ Load error: {e}")
