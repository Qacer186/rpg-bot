import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_user
from views.game_screen import GameScreenView
from utils.containers import message_view


class GameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="game", description="Otwiera główny ekran gry")
    async def game_screen(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        screen_view = GameScreenView(user_id, self.bot, current_tab="character")
        await screen_view.reload()
        await interaction.response.send_message(view=screen_view)


async def setup(bot):
    await bot.add_cog(GameCog(bot))
