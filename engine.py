import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from config import temp
from database import db

logger = logging.getLogger(__name__)

async def refresh_route_cache():
    """Caches active routes in memory to avoid DB lookups on every single message."""
    temp.CACHED_ROUTES = await db.get_routes(status='active')

@Client.on_message(filters.all & ~filters.me, group=-1)
async def dynamic_router(bot: Client, message):
    """Listens to all messages and routes them if they match an active source chat."""
    if not message.chat:
        return
    
    source_id = message.chat.id
    
    # Check memory cache for relevant active routes
    active_routes = [r for r in temp.CACHED_ROUTES if r['source_id'] == source_id]
    if not active_routes:
        return

    for route in active_routes:
        client_id = route['client_id']
        worker_client = temp.ACTIVE_CLIENTS.get(client_id)
        
        if not worker_client:
            logger.warning(f"Worker client {client_id} offline for route {route['route_id']}")
            continue
            
        # Check exclusions (Example: if text is excluded and msg is text)
        if "text" in route.get('exclusions', []) and message.text:
            continue
        if "video" in route.get('exclusions', []) and message.video:
            continue
            
        try:
            # Forward the message
            await worker_client.copy_message(
                chat_id=route['target_id'],
                from_chat_id=source_id,
                message_id=message.id
            )
            # Update last processed ID in DB
            await db.update_route_last_msg(route['route_id'], message.id)
            # Update cache to reflect new ID
            route['last_processed_msg_id'] = message.id
            
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await worker_client.copy_message(route['target_id'], source_id, message.id)
        except Exception as e:
            logger.error(f"Route {route['route_id']} failed to copy msg {message.id}: {e}")


async def catch_up_task():
    """Runs on startup. Checks for missed messages while bot was offline."""
    await refresh_route_cache()
    logger.info("Starting Catch-Up Phase for all active routes...")
    
    for route in temp.CACHED_ROUTES:
        client_id = route['client_id']
        worker_client = temp.ACTIVE_CLIENTS.get(client_id)
        
        if not worker_client:
            continue
            
        source_id = route['source_id']
        target_id = route['target_id']
        last_processed = route['last_processed_msg_id']
        
        try:
            # Get the absolute latest message ID in the source chat
            async for msg in worker_client.get_chat_history(source_id, limit=1):
                actual_latest = msg.id
                break
            else:
                continue # Chat empty
                
            if actual_latest > last_processed:
                missing_count = actual_latest - last_processed
                logger.info(f"Route {route['route_id']} is behind by {missing_count} messages. Catching up...")
                
                # Fetch missing messages in chunks
                for msg_id in range(last_processed + 1, actual_latest + 1):
                    try:
                        messages = await worker_client.get_messages(source_id, [msg_id])
                        if not messages or getattr(messages[0], 'empty', True):
                            continue
                            
                        await worker_client.copy_message(target_id, source_id, msg_id)
                        await db.update_route_last_msg(route['route_id'], msg_id)
                        await asyncio.sleep(0.5) # Delay to prevent flood wait
                        
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                    except Exception as e:
                        pass # Skip deleted/unfetchable messages
                        
            logger.info(f"Route {route['route_id']} is fully synced.")
            
        except Exception as e:
            logger.error(f"Catch-up failed for route {route['route_id']}: {e}")
            
    # Refresh cache after catch-up
    await refresh_route_cache()