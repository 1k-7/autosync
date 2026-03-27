import motor.motor_asyncio
from config import Config

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db.users
        self.clients = self.db.clients
        self.chats = self.db.chats
        self.routes = self.db.routes

    # --- Users ---
    async def add_user(self, user_id, name):
        if not await self.users.find_one({'id': user_id}):
            await self.users.insert_one({'id': user_id, 'name': name})

    # --- Clients (Bots & Userbots) ---
    async def add_client(self, user_id, client_id, is_bot, name, session_string, username=None):
        doc = {
            'id': client_id, 'user_id': user_id, 'is_bot': is_bot, 
            'name': name, 'session': session_string, 'username': username
        }
        await self.clients.update_one({'id': client_id}, {'$set': doc}, upsert=True)

    async def get_clients(self, user_id=None):
        query = {'user_id': user_id} if user_id else {}
        return [client async for client in self.clients.find(query)]

    async def delete_client(self, client_id):
        await self.clients.delete_one({'id': client_id})

    # --- Chats (Sources & Targets) ---
    async def add_chat(self, user_id, chat_id, title, username):
        doc = {'chat_id': chat_id, 'user_id': user_id, 'title': title, 'username': username}
        await self.chats.update_one({'chat_id': chat_id, 'user_id': user_id}, {'$set': doc}, upsert=True)

    async def get_chats(self, user_id):
        return [chat async for chat in self.chats.find({'user_id': user_id})]

    # --- Routes ---
    async def add_route(self, route_id, user_id, source_id, target_id, client_id, start_msg_id):
        doc = {
            'route_id': route_id, 'user_id': user_id, 
            'source_id': source_id, 'target_id': target_id, 
            'client_id': client_id, 'last_processed_msg_id': start_msg_id, 
            'status': 'active', 'exclusions': []
        }
        await self.routes.insert_one(doc)

    async def get_routes(self, user_id=None, status=None):
        query = {}
        if user_id: query['user_id'] = user_id
        if status: query['status'] = status
        return [route async for route in self.routes.find(query)]

    async def get_route(self, route_id):
        return await self.routes.find_one({'route_id': route_id})

    async def update_route_status(self, route_id, status):
        await self.routes.update_one({'route_id': route_id}, {'$set': {'status': status}})

    async def update_route_last_msg(self, route_id, msg_id):
        await self.routes.update_one({'route_id': route_id}, {'$set': {'last_processed_msg_id': msg_id}})
        
    async def delete_route(self, route_id):
        await self.routes.delete_one({'route_id': route_id})

db = Database(Config.DB_URL, Config.DB_NAME)