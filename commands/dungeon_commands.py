import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_user, regenerate_stamina
from views.dungeon_view import DungeonView
from utils.containers import message_view


class DungeonCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dungeon", description="Otwiera loch ze stałymi przeciwnikami")
    async def dungeon(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        await regenerate_stamina(user_id)
        view = DungeonView(user_id, self.bot)
        await view.reload()
        await interaction.response.send_message(view=view)
        message = await interaction.original_response()
        view.start_auto_refresh(message)


async def setup(bot):
    await bot.add_cog(DungeonCog(bot))
