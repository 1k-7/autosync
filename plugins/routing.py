import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import temp
from engine import refresh_route_cache

@Client.on_callback_query(filters.regex("^menu_routes$"))
async def cb_routes(client, query):
    routes = await db.get_routes(query.from_user.id)
    
    buttons = []
    for r in routes:
        status_icon = "🟢" if r['status'] == 'active' else "⏸"
        buttons.append([InlineKeyboardButton(f"{status_icon} Route: {r['route_id'][:6]}", callback_data=f"route_view_{r['route_id']}")])
        
    buttons.append([InlineKeyboardButton("➕ Create New Route", callback_data="route_create_step1")])
    buttons.append([InlineKeyboardButton("« Back", callback_data="menu_main")])
    
    await query.message.edit_text("**🔄 Routing Management**\nSelect a route to configure or create a new one.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^route_view_(.*)$"))
async def cb_route_view(client, query):
    route_id = query.matches[0].group(1)
    route = await db.get_route(route_id)
    if not route: return await query.answer("Route not found.", show_alert=True)
    
    text = (
        f"**Route ID:** `{route_id}`\n"
        f"**Status:** `{route['status'].upper()}`\n"
        f"**Source ID:** `{route['source_id']}`\n"
        f"**Target ID:** `{route['target_id']}`\n"
        f"**Client ID:** `{route['client_id']}`\n"
        f"**Last Sync Msg ID:** `{route['last_processed_msg_id']}`\n"
    )
    
    toggle_status = "pause" if route['status'] == 'active' else "resume"
    buttons = [
        [InlineKeyboardButton(f"{'⏸ Pause' if toggle_status=='pause' else '▶️ Resume'} Route", callback_data=f"route_toggle_{route_id}_{toggle_status}")],
        [InlineKeyboardButton("🗑 Delete Route", callback_data=f"route_delete_{route_id}")],
        [InlineKeyboardButton("« Back to Routes", callback_data="menu_routes")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^route_toggle_(.*)_(.*)$"))
async def cb_route_toggle(client, query):
    route_id = query.matches[0].group(1)
    action = query.matches[0].group(2)
    new_status = 'active' if action == 'resume' else 'paused'
    
    await db.update_route_status(route_id, new_status)
    await refresh_route_cache()
    
    if new_status == 'active':
        from engine import catch_up_task
        client.loop.create_task(catch_up_task()) 
        
    await query.answer(f"Route {new_status}!", show_alert=True)
    await cb_route_view(client, query)

@Client.on_callback_query(filters.regex("^route_delete_(.*)$"))
async def cb_route_delete(client, query):
    route_id = query.matches[0].group(1)
    await db.delete_route(route_id)
    await refresh_route_cache()
    await query.answer("Route deleted.", show_alert=True)
    await cb_routes(client, query)

# --- ROUTE CREATION WIZARD ---
@Client.on_callback_query(filters.regex("^route_create_step1$"))
async def cb_route_create_1(client, query):
    user_id = query.from_user.id
    temp.USER_STATES[user_id] = {"new_route": {}}
    
    chats = await db.get_chats(user_id)
    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"rcreate_source_{c['chat_id']}")] for c in chats]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="menu_routes")])
    
    await query.message.edit_text("**Step 1:** Select the **SOURCE** chat.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^rcreate_source_(.*)$"))
async def cb_route_create_2(client, query):
    user_id = query.from_user.id
    source_id = int(query.matches[0].group(1))
    temp.USER_STATES[user_id]["new_route"]["source_id"] = source_id
    
    chats = await db.get_chats(user_id)
    buttons = [[InlineKeyboardButton(c['title'], callback_data=f"rcreate_target_{c['chat_id']}")] for c in chats]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="menu_routes")])
    
    await query.message.edit_text("**Step 2:** Select the **TARGET** chat.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^rcreate_target_(.*)$"))
async def cb_route_create_3(client, query):
    user_id = query.from_user.id
    target_id = int(query.matches[0].group(1))
    temp.USER_STATES[user_id]["new_route"]["target_id"] = target_id
    
    clients = await db.get_clients(user_id)
    buttons = [[InlineKeyboardButton(c['name'], callback_data=f"rcreate_client_{c['id']}")] for c in clients]
    buttons.append([InlineKeyboardButton("« Cancel", callback_data="menu_routes")])
    
    await query.message.edit_text("**Step 3:** Select the **Client (Userbot)** to perform the syncing.", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^rcreate_client_(.*)$"))
async def cb_route_create_4(client, query):
    user_id = query.from_user.id
    client_id = int(query.matches[0].group(1))
    
    route_data = temp.USER_STATES[user_id]["new_route"]
    source_id = route_data["source_id"]
    target_id = route_data["target_id"]
    route_id = str(uuid.uuid4())
    
    worker_client = temp.ACTIVE_CLIENTS.get(client_id)
    if not worker_client:
        return await query.answer("Selected client is offline.", show_alert=True)
    
    start_msg_id = 0
    # FIX: Bypass history fetch if client is a regular Bot
    if not worker_client.is_bot:
        try:
            async for msg in worker_client.get_chat_history(source_id, limit=1):
                start_msg_id = msg.id
                break
        except Exception as e:
            return await query.message.edit_text(f"❌ Error accessing source chat: {e}")
    else:
        # For Bots, we set to 0. The first live message caught will calibrate it.
        start_msg_id = 0
        
    await db.add_route(route_id, user_id, source_id, target_id, client_id, start_msg_id)
    await refresh_route_cache()
    
    temp.USER_STATES.pop(user_id, None)
    await query.answer("✅ Route Created successfully!", show_alert=True)
    await cb_routes(client, query)
