import asyncio
import logging
import os
import json
import tempfile
from datetime import datetime
from database import db
from config import ADMIN_ID, DB_PATH
from batch_manager import BatchManager
from utils import safe_send_document

logger = logging.getLogger(__name__)

async def backup_loop(client, batch_manager):
    """
    Background task to backup active batches as JSON every 30 minutes.
    ONLY runs if there are active downloads/processes.
    """
    logger.info("💾 Backup task started (every 30m, only if active)")

    while True:
        try:
            await asyncio.sleep(1800)  # 30 minutes

            # Check if any active process
            active_items = batch_manager.active_downloads
            if not active_items:
                logger.info("💤 No active downloads, skipping auto-backup")
                continue

            # Get unique active batch IDs
            active_batch_ids = set()
            for key, data in active_items.items():
                if data.get('running') and data.get('batch_id'):
                    active_batch_ids.add(data['batch_id'])

            if not active_batch_ids:
                continue

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"📤 Sending backups for {len(active_batch_ids)} active batches")

            for batch_id in active_batch_ids:
                try:
                    # Get batch info to find owner
                    batch = await db.get_batch(batch_id)
                    if not batch:
                        continue

                    user_id = batch['user_id']

                    # Generate JSON backup
                    backup_json = await batch_manager.get_backup_data(batch_id)
                    batch_name = batch['batch_name']
                    filename = f"{batch_name}_backup_{datetime.now().strftime('%H%M')}.json"

                    # Create temp file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                        f.write(backup_json)
                        temp_path = f.name

                    # Send to user
                    await safe_send_document(
                        client,
                        chat_id=user_id,
                        document=temp_path,
                        file_name=filename,
                        caption=f"💾 **Auto Backup**\n\n📦 {batch_name}\n📅 {timestamp}"
                    )

                    os.remove(temp_path)
                    logger.info(f"✅ Backup sent for {batch_name} to {user_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to send backup for batch {batch_id}: {e}")

        except asyncio.CancelledError:
            logger.info("⏹️ Backup task cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Backup loop error: {e}")
            await asyncio.sleep(60)
