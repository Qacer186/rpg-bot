import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_user, create_user
from utils.containers import message_view


class StartCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start", description="Tworzy postać")
    async def start(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if user:
            await interaction.response.send_message(view=message_view("### ❌ Masz już postać\nNie możesz utworzyć drugiej postaci.", 0xE74C3C), ephemeral=True)
            return

        await create_user(user_id)
        view = message_view(
            "### 🧙 Postać utworzona!\n"
            "Powodzenia, bohaterze!\n"
            "Na start dostajesz też `5` grzybków.\n\n"
            "Użyj `/game`, żeby otworzyć główny ekran gry.",
            0x2ECC71
        )
        await interaction.response.send_message(view=view)


async def setup(bot):
    await bot.add_cog(StartCog(bot))
