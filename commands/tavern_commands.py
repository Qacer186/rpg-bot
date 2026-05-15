import discord
from discord import app_commands
from discord.ext import commands
import time
from database.db import get_user, get_random_quests, regenerate_stamina
from views.tavern_views import QuestView, create_progress_bar


class TavernCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tavern", description="Odwiedź karczmę i wybierz misję")
    async def tavern(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.followup.send("Najpierw użyj /start!", ephemeral=True)
            return

        await regenerate_stamina(user_id)
        user = await get_user(user_id)

        if user['stamina'] < 10:
            await interaction.followup.send("⚡ Za mało staminy! Odpocznij chwilę.", ephemeral=True)
            return

        quests = await get_random_quests(user_id)

        embed = discord.Embed(
            title="🍻 KARCZMA U PODPITEGO GOBLINA",
            description="═══════════════════════════════════════",
            color=0x6b4226
        )
        hp_bar = create_progress_bar(user['hp'], user['max_hp'], 15)
        stamina_bar = create_progress_bar(user['stamina'], 100, 15)

        embed.add_field(
            name="⚔️ STATYSTYKI",
            value=f"**Lvl:** {user['level']} | **EXP:** {user['exp']}\n"
                  f"**Atak:** {user['attack']} | **Obrona:** {user['defense']}",
            inline=False
        )
        embed.add_field(name="❤️ ZDROWIE", value=f"{hp_bar}\n`{user['hp']}/{user['max_hp']} HP`", inline=False)
        embed.add_field(name="⚡ STAMINA", value=f"{stamina_bar}\n`{user['stamina']}/100`", inline=False)
        embed.add_field(name="💰 PORTFEL", value=f"**{user['gold']} złota**", inline=False)
        embed.add_field(name="═══════════════════════════════════════", value="", inline=False)
        embed.add_field(name="📜 DOSTĘPNE MISJE", value="Wybierz misję z menu poniżej:", inline=False)

        for i, q in enumerate(quests, 1):
            difficulty = "🟢 ŁATWA" if q['gold'] < 100 else "🟡 ŚREDNIA" if q['gold'] < 300 else "🔴 TRUDNA"
            embed.add_field(
                name=f"**Misja {i}: {q['name']}**",
                value=f"{difficulty}\n"
                      f"⏱️ **Czas:** {q['duration']} min\n"
                      f"💰 **Złoto:** {q['gold']}\n"
                      f"✨ **EXP:** {q['exp']}",
                inline=False
            )

        view = QuestView(user, quests, self.bot)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="expedition_status", description="Sprawdź status swojej misji")
    async def expedition_status(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message("Najpierw użyj /start!", ephemeral=True)
            return

        if user['on_expedition']:
            elapsed = time.time() - user['expedition_start_time']
            remaining = user['expedition_duration'] * 60 - elapsed
            if remaining > 0:
                min_left = int(remaining // 60)
                sec_left = int(remaining % 60)
                await interaction.response.send_message(f"⚔️ Jesteś na misji! Pozostało: {min_left} min {sec_left} sek")
            else:
                await interaction.response.send_message("Misja powinna już się zakończyć! Spróbuj ponownie za chwilę.")
        else:
            await interaction.response.send_message("Nie jesteś obecnie na misji.")


async def setup(bot):
    await bot.add_cog(TavernCog(bot))
