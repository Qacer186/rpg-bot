import discord
from discord import app_commands
from discord.ext import commands

from database.db import (
    add_mushrooms,
    get_random_quests,
    get_user,
    increase_max_stamina,
    refresh_user_quests,
)
from utils.containers import message_view
from views.tavern_views import QuestView


class MushroomCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mushrooms", description="Pokazuje grzybki i ich zastosowania")
    async def mushrooms(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        text = (
            "### 🍄 Grzybki\n"
            f"Masz: `{user['mushrooms']}` grzybków.\n\n"
            "Grzybki możesz wykorzystać na:\n"
            "• pominięcie 30 minut czekania w lochu,\n"
            "• `/refresh_shop` czyli odświeżenie sklepu za `1` grzybka,\n"
            "• `/refresh_missions` czyli nowe misje w karczmie za `1` grzybka,\n"
            "• `/increase_stamina` czyli `+10` max staminy za `3` grzybki.\n\n"
            "Admin może doładować grzybki komendą `/doladuj_grzybki`."
        )
        await interaction.response.send_message(view=message_view(text, 0x2ECC71))

    @app_commands.command(name="doladuj_grzybki", description="Doładowuje grzybki graczowi, komenda dla admina")
    @app_commands.describe(ilosc="Ile grzybków dodać", gracz="Gracz, któremu chcesz dodać grzybki")
    async def doladuj_grzybki(
        self,
        interaction: discord.Interaction,
        ilosc: app_commands.Range[int, 1, 10000],
        gracz: discord.Member | None = None
    ):
        is_owner = await self.bot.is_owner(interaction.user)
        guild_permissions = getattr(interaction.user, "guild_permissions", None)
        is_admin = bool(guild_permissions and guild_permissions.administrator)

        if not is_owner and not is_admin:
            await interaction.response.send_message(
                view=message_view("❌ Tylko administrator serwera albo właściciel bota może doładowywać grzybki.", 0xE74C3C),
                ephemeral=True
            )
            return

        target = gracz or interaction.user
        target_id = str(target.id)
        user = await get_user(target_id)
        if not user:
            await interaction.response.send_message(
                view=message_view("❌ Ten gracz nie ma jeszcze postaci. Najpierw musi użyć `/start`.", 0xE74C3C),
                ephemeral=True
            )
            return

        await add_mushrooms(target_id, int(ilosc))
        user = await get_user(target_id)
        text = (
            "### 🍄 Grzybki doładowane\n"
            f"Gracz: {target.mention}\n"
            f"Dodano: `+{int(ilosc)}` grzybków\n"
            f"Aktualnie ma: `{user['mushrooms']}` grzybków"
        )
        await interaction.response.send_message(view=message_view(text, 0x2ECC71))

    @app_commands.command(name="increase_stamina", description="Zwiększa maksymalną staminę za 3 grzybki")
    async def increase_stamina(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        ok, message = await increase_max_stamina(user_id)
        user = await get_user(user_id)
        if not ok:
            await interaction.response.send_message(view=message_view(f"❌ {message}", 0xE74C3C), ephemeral=True)
            return

        text = (
            "### ⚡ Stamina zwiększona\n"
            f"{message}\n\n"
            f"Nowa stamina: `{user['stamina']}/{user['max_stamina']}`\n"
            f"🍄 Grzybki: `{user['mushrooms']}`"
        )
        await interaction.response.send_message(view=message_view(text, 0x2ECC71))

    @app_commands.command(name="refresh_missions", description="Odświeża misje w karczmie za 1 grzybka")
    async def refresh_missions(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.followup.send(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if user['on_expedition']:
            await interaction.followup.send(view=message_view("⚠️ Masz aktywną misję. Nie możesz teraz odświeżyć karczmy.", 0xE67E22), ephemeral=True)
            return

        ok, message = await refresh_user_quests(user_id)
        if not ok:
            await interaction.followup.send(view=message_view(f"❌ {message}", 0xE74C3C), ephemeral=True)
            return

        user = await get_user(user_id)
        quests = await get_random_quests(user_id)
        footer = f"### 🍄 Misje odświeżone\n{message}\nPozostałe grzybki: `{user['mushrooms']}`"
        view = QuestView(user, quests, self.bot, footer=footer)
        await interaction.followup.send(view=view)


async def setup(bot):
    await bot.add_cog(MushroomCog(bot))
