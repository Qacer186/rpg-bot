import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_user, create_user


class StartCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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


async def setup(bot):
    await bot.add_cog(StartCog(bot))
