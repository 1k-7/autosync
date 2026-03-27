from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import Config, temp

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Clients (Bots/Userbots)", callback_data="menu_clients")],
        [InlineKeyboardButton("📂 Manage Chats", callback_data="menu_chats")],
        [InlineKeyboardButton("🔄 Routing (Pairs)", callback_data="menu_routes")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="menu_stats")]
    ])

@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    if user_id not in Config.OWNER_ID:
        return await message.reply("Unauthorized access.")
        
    await db.add_user(user_id, message.from_user.first_name)
    temp.USER_STATES.pop(user_id, None) # Clear states
    
    text = f"Welcome to **24x7 Auto-Sync Engine**, {message.from_user.first_name}.\n\nChoose an option below:"
    await message.reply(text, reply_markup=main_menu_keyboard())

@Client.on_callback_query(filters.regex("^menu_main$"))
async def cb_main(client, query):
    temp.USER_STATES.pop(query.from_user.id, None)
    await query.message.edit_text("Welcome to **24x7 Auto-Sync Engine**.", reply_markup=main_menu_keyboard())

@Client.on_callback_query(filters.regex("^menu_stats$"))
async def cb_stats(client, query):
    routes = await db.get_routes()
    clients = await db.get_clients()
    chats = await db.get_chats(query.from_user.id)
    
    text = (
        "**📊 System Statistics**\n\n"
        f"Active Clients: `{len(clients)}`\n"
        f"Registered Chats: `{len(chats)}`\n"
        f"Total Routes: `{len(routes)}`\n"
    )
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="menu_main")]]))