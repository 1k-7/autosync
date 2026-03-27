import os

class Config:
    API_ID = int(os.environ.get("API_ID", "123456")) # Replace with your API ID
    API_HASH = os.environ.get("API_HASH", "your_api_hash")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
    BOT_SESSION = os.environ.get("BOT_SESSION", "auto_sync_bot")
    DB_URL = os.environ.get("DB_URL", "mongodb+srv://...")
    DB_NAME = os.environ.get("DB_NAME", "AutoSyncCluster")
    OWNER_ID = [int(id) for id in os.environ.get("OWNER_ID", "123456789").split()]

class temp(object):
    USER_STATES = {}
    ACTIVE_CLIENTS = {} # {client_id: PyrogramClientInstance}
    CACHED_ROUTES = []  # In-memory cache of active routes for speed