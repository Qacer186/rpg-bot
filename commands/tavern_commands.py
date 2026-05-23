import discord
from discord import app_commands
from discord.ext import commands
import math
import time
from database.db import get_user, get_random_quests, regenerate_stamina
from views.tavern_views import QuestView
from utils.containers import message_view


class TavernCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tavern", description="Odwiedź karczmę i wybierz misję")
    async def tavern(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.followup.send(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if user['on_expedition']:
            await interaction.followup.send(view=message_view("⚠️ Masz już aktywną misję. Najpierw ją zakończ albo sprawdź `/expedition_status`.", 0xE67E22), ephemeral=True)
            return

        await regenerate_stamina(user_id)
        user = await get_user(user_id)

        if user['stamina'] < 10:
            await interaction.followup.send(view=message_view("⚡ Za mało staminy! Odpocznij chwilę.", 0xE67E22), ephemeral=True)
            return

        quests = await get_random_quests(user_id)
        view = QuestView(user, quests, self.bot)
        await interaction.followup.send(view=view)

    @app_commands.command(name="expedition_status", description="Sprawdź status swojej misji")
    async def expedition_status(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if user['on_expedition']:
            elapsed = time.time() - user['expedition_start_time']
            remaining = max(0, math.ceil(user['expedition_duration'] * 60 - elapsed))
            if remaining > 0:
                min_left = remaining // 60
                sec_left = remaining % 60
                await interaction.response.send_message(view=message_view(f"### ⚔️ Misja w toku\nPozostało: `{min_left} min {sec_left} sek`", 0x6B4226))
            else:
                await interaction.response.send_message(view=message_view("### ✅ Misja prawie zakończona\nPozostało: `0 sek`\nWynik powinien pojawić się za chwilę.", 0x2ECC71))
        else:
            await interaction.response.send_message(view=message_view("### 📜 Brak aktywnej misji\nNie jesteś obecnie na misji.", 0x95A5A6))


async def setup(bot):
    await bot.add_cog(TavernCog(bot))
