import aiosqlite
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_done = False
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection"""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()
    
    async def init_db(self):
        """Initialize database with WAL mode"""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=FULL")
            
            # User sessions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id INTEGER PRIMARY KEY,
                    mode TEXT,
                    data TEXT,
                    updated_at DATETIME
                )
            """)
            
            # Batches
            await db.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    batch_name TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    destination_id INTEGER,
                    quality TEXT,
                    schedule_time TEXT,
                    custom_caption TEXT,
                    caption_style TEXT,
                    is_active INTEGER DEFAULT 1,
                    added_at DATETIME NOT NULL
                )
            """)
            
            await db.execute("CREATE INDEX IF NOT EXISTS idx_batches_user_id ON batches(user_id)")
            
            # ✅ ENHANCED: Sent content with status tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sent_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    destination_id INTEGER,
                    content_title TEXT,
                    content_url TEXT NOT NULL,
                    status TEXT DEFAULT 'success',
                    sent_at DATETIME,
                    UNIQUE(batch_id, content_url)
                )
            """)
            
            # ✅ Add status column if it doesn't exist (migration)
            try:
                await db.execute("ALTER TABLE sent_content ADD COLUMN status TEXT DEFAULT 'success'")
                logger.info("✅ Added status column to sent_content")
            except:
                pass  # Column already exists
            
            await db.commit()
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            
            logger.info("✅ Database initialized with status tracking")
    
    # === USER SESSION ===
    async def save_user_session(self, user_id: int, mode: str, data: dict):
        """Save session"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_sessions 
                (user_id, mode, data, updated_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, mode, json.dumps(data), datetime.now()))
            await db.commit()
    
    async def get_user_session(self, user_id: int) -> Optional[Dict]:
        """Get session"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT mode, data FROM user_sessions WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {'mode': row[0], 'data': json.loads(row[1])}
        return None
    
    async def clear_user_session(self, user_id: int):
        """Clear session"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            await db.commit()
    
    # === BATCH MANAGEMENT ===
    async def add_batch(self, batch_id: str, batch_name: str, user_id: int):
        """Add batch"""
        try:
            logger.info(f"💾 Saving batch for user {user_id}")
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA synchronous=FULL")
                
                await db.execute("""
                    INSERT OR REPLACE INTO batches 
                    (batch_id, batch_name, user_id, added_at)
                    VALUES (?, ?, ?, ?)
                """, (batch_id, batch_name, user_id, datetime.now()))
                
                await db.commit()
                await db.execute("PRAGMA wal_checkpoint(FULL)")
                
                logger.info(f"✅ Batch saved for user {user_id}")
                return True
                        
        except Exception as e:
            logger.error(f"❌ Save error: {e}", exc_info=True)
            return False
    
    async def get_batch(self, batch_id: str) -> Optional[Dict]:
        """Get batch"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM batches WHERE batch_id = ?",
                (batch_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'batch_id': row[0], 'batch_name': row[1],
                        'user_id': row[2], 'destination_id': row[3],
                        'quality': row[4], 'schedule_time': row[5],
                        'custom_caption': row[6], 'caption_style': row[7],
                        'is_active': row[8], 'added_at': row[9]
                    }
        return None
    
    async def get_user_batches(self, user_id: int) -> List[Dict]:
        """Get user batches"""
        try:
            logger.info(f"🔍 Fetching batches for user {user_id}")
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT batch_id, batch_name, is_active FROM batches WHERE user_id = ? ORDER BY added_at DESC",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = [
                        {'batch_id': r[0], 'batch_name': r[1], 'is_active': r[2]}
                        for r in rows
                    ]
                    
                    logger.info(f"✅ Found {len(result)} batches")
                    return result
                    
        except Exception as e:
            logger.error(f"❌ Fetch error: {e}", exc_info=True)
            return []
    
    async def update_batch_setting(self, batch_id: str, key: str, value):
        """Update setting"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE batches SET {key} = ? WHERE batch_id = ?", (value, batch_id))
            await db.commit()
    
    async def remove_batch(self, batch_id: str):
        """Remove batch"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM batches WHERE batch_id = ?", (batch_id,))
            await db.execute("DELETE FROM sent_content WHERE batch_id = ?", (batch_id,))
            await db.commit()
            logger.info(f"🗑️ Removed batch: {batch_id}")
    
    # ✅ ENHANCED: Content tracking with status
    async def mark_content_sent(self, batch_id: str, destination_id: int, title: str, url: str, status: str = 'success'):
        """Mark content as sent with status"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO sent_content 
                    (batch_id, destination_id, content_title, content_url, status, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (batch_id, destination_id, title, url, status, datetime.now()))
                await db.commit()
        except Exception as e:
            logger.error(f"Mark sent error: {e}")
    
    async def is_content_sent(self, batch_id: str, url: str) -> bool:
        """Check if content was successfully sent"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status FROM sent_content WHERE batch_id = ? AND content_url = ?",
                (batch_id, url)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None and row[0] == 'success'
    
    async def get_failed_content(self, batch_id: str) -> List[str]:
        """Get list of failed content URLs"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT content_url FROM sent_content WHERE batch_id = ? AND status = 'failed'",
                (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def get_batch_stats(self, batch_id: str) -> Dict:
        """Get stats"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM sent_content WHERE batch_id = ? AND status = 'success'",
                (batch_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return {'total_sent': row[0] or 0}
    
    async def reset_batch_progress(self, batch_id: str):
        """Reset batch progress (clear sent content)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM sent_content WHERE batch_id = ?", (batch_id,))
                await db.commit()
                logger.info(f"🔄 Reset progress for batch {batch_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Reset batch error: {e}")
            return False

    # ✅ NEW: Restore batch settings from backup
    async def restore_batch_settings(self, batch_id: str, settings: Dict):
        """Restore batch settings from backup"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE batches 
                    SET destination_id = ?,
                        quality = ?,
                        schedule_time = ?,
                        custom_caption = ?,
                        caption_style = ?,
                        is_active = ?
                    WHERE batch_id = ?
                """, (
                    settings.get('destination_id'),
                    settings.get('quality'),
                    settings.get('schedule_time'),
                    settings.get('custom_caption'),
                    settings.get('caption_style'),
                    settings.get('is_active', 0),  # Keep inactive after restore
                    batch_id
                ))
                await db.commit()
                logger.info(f"✅ Restored settings for batch {batch_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Restore settings error: {e}")
            return False

# Global instance
db = Database()
