import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
from database.db import init_db

# Konfiguracja logowania
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"logs/bot_{discord.utils.utcnow().strftime('%Y-%m-%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_rpg')

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 707527819114315838

class RpgBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        
        # Automatyczne ładowanie Cogs z folderu commands/
        for filename in os.listdir('./commands'):
            if filename.endswith('.py'):
                await self.load_extension(f'commands.{filename[:-3]}')
                logger.info(f'Załadowano moduł: {filename}')

        # Synchronizacja komend dla serwera
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Zsynchronizowano {len(synced)} komend slash.")

    async def on_ready(self):
        logger.info(f"Zalogowano jako {self.user} (ID: {self.user.id})")

bot = RpgBot()
bot.run(TOKEN)