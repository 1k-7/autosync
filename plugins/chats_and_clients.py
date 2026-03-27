import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import db
from config import temp
from client_manager import start_all_clients

# --- CLIENTS MANAGEMENT ---
@Client.on_callback_query(filters.regex("^menu_clients$"))
async def cb_clients(client, query):
    clients = await db.get_clients(query.from_user.id)
    text = "**🤖 Manage Clients**\n\n"
    for c in clients:
        text += f"• `{c['name']}` ({c['id']}) - {'Bot' if c['is_bot'] else 'Userbot'}\n"
        
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Userbot Session", callback_data="client_add_userbot")],
        [InlineKeyboardButton("« Back", callback_data="menu_main")]
    ])
    await query.message.edit_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^client_add_userbot$"))
async def cb_add_userbot(client, query):
    msg = await query.message.edit_text("Send your Pyrogram V2 String Session.\n\nType /cancel to abort.")
    temp.USER_STATES[query.from_user.id] = {"state": "awaiting_session", "msg_id": msg.id}

# --- CHATS MANAGEMENT ---
@Client.on_callback_query(filters.regex("^menu_chats$"))
async def cb_chats(client, query):
    chats = await db.get_chats(query.from_user.id)
    text = "**📂 Registered Chats**\n\n"
    for c in chats:
        text += f"• {c['title']} (`{c['chat_id']}`)\n"
        
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Register New Chat", callback_data="chat_add")],
        [InlineKeyboardButton("« Back", callback_data="menu_main")]
    ])
    await query.message.edit_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^chat_add$"))
async def cb_add_chat(client, query):
    msg = await query.message.edit_text("Forward a message from the channel/group you want to register.\n\nType /cancel to abort.")
    temp.USER_STATES[query.from_user.id] = {"state": "awaiting_chat_fwd", "msg_id": msg.id}

# --- STATE INPUT HANDLER ---
@Client.on_message(filters.private & filters.incoming, group=1)
async def state_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state_obj = temp.USER_STATES.get(user_id)
    if not state_obj: return
    
    state = state_obj['state']
    
    if message.text == "/cancel":
        temp.USER_STATES.pop(user_id, None)
        return await message.reply("Action cancelled. Send /start")

    if state == "awaiting_session":
        session_string = message.text
        try:
            test_client = Client("test", session_string=session_string, in_memory=True)
            await test_client.start()
            me = await test_client.get_me()
            await db.add_client(user_id, me.id, False, me.first_name, session_string, me.username)
            await test_client.stop()
            
            await start_all_clients() # Restart engine to load new client
            await message.reply(f"✅ Successfully added Userbot: {me.first_name}")
        except Exception as e:
            await message.reply(f"❌ Invalid session: {e}")
        finally:
            temp.USER_STATES.pop(user_id, None)
            
    elif state == "awaiting_chat_fwd":
        if not message.forward_from_chat:
            return await message.reply("❌ Please forward a message from a chat.")
            
        chat = message.forward_from_chat
        await db.add_chat(user_id, chat.id, chat.title or chat.first_name, chat.username)
        await message.reply(f"✅ Registered chat: {chat.title or chat.first_name} ({chat.id})")
        temp.USER_STATES.pop(user_id, None)