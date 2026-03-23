import discord
from discord import app_commands
from discord.ext import commands
import random

from database.db import get_user, create_user, get_leaderboard, buy_item, get_user_inventory, update_user, use_item, get_all_items, get_item_by_id, toggle_equip_item
from views.fight_view import FightView
from services.monster_service import get_random_monster
from services.rabbitmq import send_to_queue

class RPGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def create_progress_bar(current, maximum, length=10):
        filled = int(length * current / maximum)
        return "🟩" * filled + "⬜" * (length - filled)

    @app_commands.command(name="start", description="Tworzy postać")
    async def start(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if user:
            await interaction.response.send_message("❌ Już masz postać!", ephemeral=True)
        else:
            await create_user(user_id)
            embed = discord.Embed(title="🧙 Postać utworzona!", description="Powodzenia, bohaterze!", color=0x00ff00)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="profile", description="Pokazuje profil gracza")
    async def profile(self, interaction: discord.Interaction):
        user = await get_user(str(interaction.user.id))
        if not user:
            await interaction.response.send_message("Użyj /start!", ephemeral=True)
            return

        embed = discord.Embed(title=f"👤 Profil {interaction.user.name}", color=0x3498db)
        stamina_bar = self.create_progress_bar(user['stamina'], 100)
        
        embed.add_field(name="🎯 Statystyki", value=f"**Lvl:** {user['level']} | **EXP:** {user['exp']}", inline=True)
        embed.add_field(name="⚔️ Bojowe", value=f"**Atak:** {user['attack']} | **Obrona:** {user['defense']}", inline=True)
        embed.add_field(name="⚡ Stamina", value=f"{stamina_bar} ({user['stamina']}/100)", inline=False)
        embed.add_field(name="💰 Portfel", value=f"{user['gold']} złota", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="fight", description="Walcz z potworem z D&D API")
    async def fight(self, interaction: discord.Interaction):
        user = await get_user(str(interaction.user.id))
        if not user or user['stamina'] < 10:
            await interaction.response.send_message("Brak sił (stamina < 10)!", ephemeral=True)
            return

        await interaction.response.defer()
        monster = await get_random_monster()
        if not monster:
            monster = {"name": "Zły Cień", "hp": 30, "attack": 5, "gold": 10, "image": None}

        # --- RABBITMQ LOGIC ---
        # Wysyłamy info o walce do kolejki (Punkt 5 planu)
        fight_log = {
            "user_id": user['discord_id'],
            "monster_name": monster['name'],
            "action": "start_fight"
        }
        send_to_queue('fight_logs', fight_log)
        # ----------------------

        view = FightView(user, monster)
        embed = discord.Embed(title=f"⚔️ Napotykasz: {monster['name']}", color=0xe74c3c)
        embed.add_field(name="👾 Potwór", value=f"❤️ HP: {monster['hp']} | ⚔️ Atak: {monster['attack']}")
        if monster['image']: embed.set_thumbnail(url=monster['image'])
        
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="shop", description="Otwiera sklep")
    async def shop(self, interaction: discord.Interaction):
        items = await get_all_items()

        embed = discord.Embed(title="🛒 Sklep", color=0xf1c40f)
        for item in items:
            bonus = f"⚔️ +{item['atk_bonus']}" if item['atk_bonus'] > 0 else f"🛡️ +{item['def_bonus']}"
            embed.add_field(name=f"{item['name']} (ID: {item['id']})", value=f"Cena: {item['price']} | {bonus}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Kupuje przedmiot")
    async def buy(self, interaction: discord.Interaction, item_id: int):
        user = await get_user(str(interaction.user.id))
        item = await get_item_by_id(item_id)

        if not item:
            await interaction.response.send_message("❌ Nie ma takiego przedmiotu!", ephemeral=True)
            return

        if user['gold'] < item['price']:
            await interaction.response.send_message("❌ Nie masz wystarczająco złota!", ephemeral=True)
            return

        await buy_item(str(interaction.user.id), item_id, item['price'])
        await interaction.response.send_message(f"✅ Kupiono: {item['name']}!")

    @app_commands.command(name="inventory", description="Twój ekwipunek")
    async def inventory(self, interaction: discord.Interaction):
        items = await get_user_inventory(str(interaction.user.id))
        if not items:
            await interaction.response.send_message("Pusto!", ephemeral=True)
            return

        embed = discord.Embed(title="🎒 Ekwipunek", color=0x95a5a6)
        for item in items:
            status = "✅ Założone" if item['is_equipped'] else "📦 W torbie"
            embed.add_field(name=item['name'], value=status, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="equip", description="Zakłada lub zdejmuje przedmiot")
    async def equip(self, interaction: discord.Interaction, item_name: str):
        user_id = str(interaction.user.id)
        item_name_found, status = await toggle_equip_item(user_id, item_name)

        if not item_name_found:
            await interaction.response.send_message("Nie masz tego przedmiotu!", ephemeral=True)
            return

        action = "Założono" if status else "Zdjęto"
        await interaction.response.send_message(f"✅ **{action}:** {item_name_found}")

    @app_commands.command(name="heal", description="Używa mikstury HP")
    async def heal(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if await use_item(user_id, 'Mikstura HP'):
            await update_user(user_id, hp=user['max_hp'])
            await interaction.response.send_message("❤️ HP odnowione!")
        else:
            await interaction.response.send_message("❌ Nie masz mikstur!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RPGCog(bot))