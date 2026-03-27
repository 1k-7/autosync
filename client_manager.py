import asyncio
import logging
from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram import filters
from config import Config, temp
from database import db

logger = logging.getLogger(__name__)

async def start_all_clients():
    """Initializes and starts all saved userbots and bots from the database."""
    from engine import route_message # Import the live listener
    
    clients_data = await db.get_clients()
    for data in clients_data:
        try:
            client = Client(
                name=str(data['id']),
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=data['session'] if not data['is_bot'] else None,
                bot_token=data['session'] if data['is_bot'] else None,
                in_memory=True
            )
            
            # Attach metadata to the client object for the engine to read
            client.client_id = data['id']
            client.is_bot = data['is_bot']
            
            # Attach the live message listener directly to THIS client
            client.add_handler(MessageHandler(route_message, filters.all & ~filters.me))
            
            await client.start()
            temp.ACTIVE_CLIENTS[data['id']] = client
            logger.info(f"Started client: {data['name']} ({data['id']})")
        except Exception as e:
            logger.error(f"Failed to start client {data['id']}: {e}")

async def stop_all_clients():
    for client_id, client in temp.ACTIVE_CLIENTS.items():
        try:
            await client.stop()
        except:
            pass
