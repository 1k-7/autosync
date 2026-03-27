import asyncio
import logging
from pyrogram.errors import FloodWait
from config import temp
from database import db

logger = logging.getLogger(__name__)

async def refresh_route_cache():
    """Caches active routes in memory to avoid DB lookups on every single message."""
    temp.CACHED_ROUTES = await db.get_routes(status='active')

async def route_message(client, message):
    """The live listener attached to each individual client."""
    if not message.chat: return
    
    source_id = message.chat.id
    client_id = client.client_id
    
    # Check memory cache for relevant active routes assigned to THIS client
    active_routes = [r for r in temp.CACHED_ROUTES if r['source_id'] == source_id and r['client_id'] == client_id]
    if not active_routes: return

    for route in active_routes:
        # Exclusions Logic
        if "text" in route.get('exclusions', []) and message.text: continue
        if "video" in route.get('exclusions', []) and message.video: continue
            
        # Infinite retry loop implementation from regix.py
        while True:
            try:
                await client.copy_message(
                    chat_id=route['target_id'],
                    from_chat_id=source_id,
                    message_id=message.id
                )
                await db.update_route_last_msg(route['route_id'], message.id)
                route['last_processed_msg_id'] = message.id
                break
                
            except FloodWait as e:
                wait_seconds = e.value + 1
                logger.warning(f"FloodWait hit! Sleeping for {wait_seconds}s...")
                await asyncio.sleep(wait_seconds)
            except Exception as e:
                logger.error(f"Route {route['route_id']} failed to copy msg {message.id}: {e}")
                break


async def catch_up_task():
    """Runs on startup. Checks for missed messages while bot was offline."""
    await refresh_route_cache()
    logger.info("Starting Catch-Up Phase for all active routes...")
    
    for route in temp.CACHED_ROUTES:
        client_id = route['client_id']
        worker_client = temp.ACTIVE_CLIENTS.get(client_id)
        if not worker_client: continue
            
        # Optimization: Regular bots cannot fetch history to catch up.
        if worker_client.is_bot:
            continue
            
        source_id = route['source_id']
        target_id = route['target_id']
        last_processed = route['last_processed_msg_id']
        
        if last_processed == 0: continue # No calibration point set yet
        
        try:
            actual_latest = 0
            async for msg in worker_client.get_chat_history(source_id, limit=1):
                actual_latest = msg.id
                break
                
            if actual_latest > last_processed:
                missing_count = actual_latest - last_processed
                logger.info(f"Route {route['route_id']} is behind by {missing_count} messages. Catching up...")
                
                # Fetch missing messages in chunks of 200 (from regix.py optimization)
                for k in range(last_processed + 1, actual_latest + 1, 200):
                    chunk = list(range(k, min(k + 200, actual_latest + 1)))
                    messages = await worker_client.get_messages(source_id, chunk)
                    
                    for msg in messages:
                        if getattr(msg, 'empty', True): continue
                            
                        # Infinite retry loop for catch-up phase
                        while True:
                            try:
                                await worker_client.copy_message(target_id, source_id, msg.id)
                                await db.update_route_last_msg(route['route_id'], msg.id)
                                route['last_processed_msg_id'] = msg.id
                                await asyncio.sleep(0.5) # Built-in delay
                                break
                            except FloodWait as e:
                                wait_seconds = e.value + 1
                                logger.warning(f"Catch-up FloodWait! Sleeping for {wait_seconds}s...")
                                await asyncio.sleep(wait_seconds)
                            except Exception as e:
                                break
                                
            logger.info(f"Route {route['route_id']} is fully synced.")
            
        except Exception as e:
            logger.error(f"Catch-up failed for route {route['route_id']}: {e}")
            
    # Refresh cache after catch-up
    await refresh_route_cache()
