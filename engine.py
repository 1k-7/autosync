import asyncio
import logging
from pyrogram.errors import FloodWait
from config import temp
from database import db

logger = logging.getLogger(__name__)

async def refresh_route_cache():
    """Caches active routes in memory to avoid DB lookups on every single message."""
    temp.CACHED_ROUTES = await db.get_routes(status='active')
    logger.info(f"🔄 Route Cache Refreshed. Active routes in memory: {len(temp.CACHED_ROUTES)}")

async def resolve_peer_safe(client, chat_id):
    """
    Implements the exact get_chat_safe logic from the reference repo's regix.py.
    """
    try:
        await client.get_chat(chat_id)
        logger.info(f"✅ Successfully resolved and cached peer: {chat_id} via get_chat")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if "peer id invalid" in error_msg or "peer_id_invalid" in error_msg:
            if not getattr(client, 'is_bot', False):
                logger.info(f"⚠️ Peer {chat_id} not cached via get_chat. Scanning dialogs (Userbot mode)...")
                try:
                    async for dialog in client.get_dialogs(limit=500):
                        if dialog.chat.id == chat_id:
                            logger.info(f"✅ Successfully resolved peer: {chat_id} via dialogs")
                            return True
                except Exception as dialog_err:
                    logger.error(f"Dialog scan failed: {dialog_err}")
            else:
                logger.error(f"❌ Target {chat_id} is inaccessible. The bot is either not a member, or lacking permissions.")
            return False
        else:
            logger.error(f"❌ get_chat failed for {chat_id}: {e}")
            # Final Fallback for string usernames
            if isinstance(chat_id, str):
                try:
                    await client.get_chat(chat_id)
                    return True
                except:
                    pass
            return False

async def route_message(client, message):
    """The live listener attached to each individual client."""
    if not message.chat: return
    
    source_id = message.chat.id
    client_id = getattr(client, 'client_id', None)
    
    # RAW DEBUGGER
    logger.info(f"🔎 RAW DEBUG: Client {client_id} saw a message in Chat ID: {source_id}")
    
    # Check memory cache for relevant active routes assigned to THIS client
    active_routes = [r for r in temp.CACHED_ROUTES if r['source_id'] == source_id and r['client_id'] == client_id]
    
    if not active_routes: 
        return

    logger.info(f"📥 Message {message.id} MATCHED an active route in Source: {source_id}. Processing...")

    for route in active_routes:
        if "text" in route.get('exclusions', []) and message.text: 
            logger.info(f"⏭ Skipped message {message.id} due to 'text' exclusion.")
            continue
        if "video" in route.get('exclusions', []) and message.video: 
            logger.info(f"⏭ Skipped message {message.id} due to 'video' exclusion.")
            continue
            
        while True:
            try:
                # Switched to explicit client invocation to prevent context mismatches
                await client.copy_message(chat_id=route['target_id'], from_chat_id=source_id, message_id=message.id)
                await db.update_route_last_msg(route['route_id'], message.id)
                route['last_processed_msg_id'] = message.id
                logger.info(f"✅ Forwarded message {message.id} to Target: {route['target_id']}")
                break
                
            except FloodWait as e:
                wait_seconds = e.value + 1
                logger.warning(f"⏳ FloodWait hit! Sleeping for {wait_seconds}s...")
                await asyncio.sleep(wait_seconds)
                
            except Exception as e:
                # Catch ALL peer invalid errors (Both ValueError cache misses and Telegram API 400s)
                error_msg = str(e).lower()
                if "peer id invalid" in error_msg or "peer_id_invalid" in error_msg:
                    logger.warning(f"⚠️ Target {route['target_id']} not cached. Attempting to resolve...")
                    is_resolved = await resolve_peer_safe(client, route['target_id'])
                    
                    if is_resolved:
                        try:
                            await client.copy_message(chat_id=route['target_id'], from_chat_id=source_id, message_id=message.id)
                            await db.update_route_last_msg(route['route_id'], message.id)
                            route['last_processed_msg_id'] = message.id
                            logger.info(f"✅ Forwarded message {message.id} to Target: {route['target_id']} (After Resolving Peer)")
                            break
                        except Exception as retry_err:
                            logger.error(f"❌ Failed to copy after peer resolution: {retry_err}")
                            break
                    else:
                        logger.error(f"❌ FATAL: Target {route['target_id']} could not be resolved.")
                        break
                else:
                    logger.error(f"❌ Route {route['route_id']} failed to copy msg {message.id}: {e}")
                    break

async def catch_up_task():
    """Runs on startup. Checks for missed messages while bot was offline."""
    await refresh_route_cache()
    logger.info("Starting Catch-Up Phase for all active routes...")
    
    for route in temp.CACHED_ROUTES:
        client_id = route['client_id']
        worker_client = temp.ACTIVE_CLIENTS.get(client_id)
        if not worker_client: continue
            
        if getattr(worker_client, 'is_bot', False): continue
            
        source_id = route['source_id']
        target_id = route['target_id']
        last_processed = route['last_processed_msg_id']
        
        if last_processed == 0: continue 
        
        try:
            actual_latest = 0
            async for msg in worker_client.get_chat_history(source_id, limit=1):
                actual_latest = msg.id
                break
                
            if actual_latest > last_processed:
                missing_count = actual_latest - last_processed
                logger.info(f"⚡ Route {route['route_id']} is behind by {missing_count} messages. Catching up...")
                
                for k in range(last_processed + 1, actual_latest + 1, 200):
                    chunk = list(range(k, min(k + 200, actual_latest + 1)))
                    messages = await worker_client.get_messages(source_id, chunk)
                    
                    for msg in messages:
                        if getattr(msg, 'empty', True): continue
                            
                        while True:
                            try:
                                await worker_client.copy_message(chat_id=target_id, from_chat_id=source_id, message_id=msg.id)
                                await db.update_route_last_msg(route['route_id'], msg.id)
                                route['last_processed_msg_id'] = msg.id
                                await asyncio.sleep(0.5) 
                                break
                            except FloodWait as e:
                                wait_seconds = e.value + 1
                                logger.warning(f"⏳ Catch-up FloodWait! Sleeping for {wait_seconds}s...")
                                await asyncio.sleep(wait_seconds)
                            except Exception as e:
                                error_msg = str(e).lower()
                                if "peer id invalid" in error_msg or "peer_id_invalid" in error_msg:
                                    is_resolved = await resolve_peer_safe(worker_client, target_id)
                                    if is_resolved:
                                        try:
                                            await worker_client.copy_message(chat_id=target_id, from_chat_id=source_id, message_id=msg.id)
                                            await db.update_route_last_msg(route['route_id'], msg.id)
                                            route['last_processed_msg_id'] = msg.id
                                            await asyncio.sleep(0.5)
                                            break
                                        except Exception:
                                            break 
                                    else:
                                        break
                                else:
                                    break
                                
            logger.info(f"✅ Route {route['route_id']} is fully synced.")
            
        except Exception as e:
            logger.error(f"❌ Catch-up failed for route {route['route_id']}: {e}")
            
    await refresh_route_cache()
