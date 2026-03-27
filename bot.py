import asyncio
import logging
from pyrogram import Client, idle
from config import Config
from client_manager import start_all_clients, stop_all_clients
from engine import catch_up_task

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class AutoSyncBot(Client):
    def __init__(self):
        super().__init__(
            Config.BOT_SESSION,
            api_hash=Config.API_HASH,
            api_id=Config.API_ID,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "plugins"} # Loads plugins/menu.py, etc.
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        logging.info(f"Bot started as @{me.username}")
        
        # Start all sub-clients (userbots)
        await start_all_clients()
        
        # Run crash recovery catch-up asynchronously
        asyncio.create_task(catch_up_task())

    async def stop(self, *args):
        await stop_all_clients()
        await super().stop()
        logging.info("Bot stopped.")

if __name__ == "__main__":
    bot = AutoSyncBot()
    bot.run()