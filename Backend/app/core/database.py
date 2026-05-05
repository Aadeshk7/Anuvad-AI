from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        """Connect to MongoDB"""
        try:
            print(f"DEBUG: Connecting to MongoDB at {settings.mongo_uri}")
            self.client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[settings.mongo_db_name]
            # Ping database to verify connection
            await self.client.admin.command('ping')
            print(f"DEBUG: SUCCESS: Successfully connected to database: {settings.mongo_db_name}")
        except Exception as e:
            print(f"DEBUG: ERROR: FAILED to connect to MongoDB: {e}")
            raise e

    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()

    def get_users_collection(self):
        """Returns the users collection"""
        return self.db["users"]

    def get_projects_collection(self):
        """Returns the projects collection"""
        return self.db["projects"]

db_manager = DatabaseManager()
