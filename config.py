import os
from pathlib import Path

# Bot Configuration
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", "10000"))

# Directories
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = Path("bot_data.db")

# API Endpoints for Auto Mode
COURSES_API = "https://backend.multistreaming.site/api/courses/"
CLASSES_API = "https://backend.multistreaming.site/api/courses/{}/classes?populate-full"

# Quality Settings (NO CONVERSION - Original Quality)
QUALITY_PRESETS = {
    "480p": {"label": "480p", "height": 480},
    "720p": {"label": "720p", "height": 720},
    "1080p": {"label": "1080p (Original)", "height": 1080}
}

# File Type Detection
SUPPORTED_TYPES = {
    'video': [
        '.m3u8', '.ts', '.mp4', '.mkv', '.avi', '.mov', 
        '.wmv', '.flv', '.webm', '.m4v', '.3gp'
    ],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'],
    'document': ['.pdf', '.doc', '.docx', '.txt', '.zip', '.rar']
}

# Download Settings
CHUNK_SIZE = 5242880  # 5MB
MAX_WORKERS = 4
CONNECTION_TIMEOUT = 3600
MAX_RETRIES = 3

# Upload Settings
UPLOAD_CHUNK_SIZE = 2097152  # 2MB
TELEGRAM_FILE_LIMIT = 2000  # 2GB in MB
SAFE_SPLIT_SIZE = 1900  # Split at 1.9GB

# Progress Settings
PROGRESS_UPDATE_INTERVAL = 10.0

# Thumbnail Settings
THUMB_WIDTH = 320
THUMB_HEIGHT = 180

# Auto Mode Settings
DEFAULT_CHECK_INTERVAL = 3600  # 1 hour in seconds
BACKUP_FILE = Path("bot_backup.json")
