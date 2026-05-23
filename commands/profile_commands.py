import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_user, get_equipped_bonuses, get_leaderboard, regenerate_stamina, exp_info_line
from utils.containers import message_view


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def create_progress_bar(current, maximum, length=10):
        if maximum <= 0:
            return "⬜" * length
        filled = int(length * current / maximum)
        filled = max(0, min(length, filled))
        return "🟩" * filled + "⬜" * (length - filled)

    @app_commands.command(name="profile", description="Pokazuje profil gracza")
    async def profile(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await regenerate_stamina(user_id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        bonuses = await get_equipped_bonuses(user_id)
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        hp_bar = self.create_progress_bar(user['hp'], user['max_hp'], 15)
        stamina_bar = self.create_progress_bar(user['stamina'], user['max_stamina'], 15)

        text = (
            f"### 👤 PROFIL: {interaction.user.name}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "**🎯 Podstawowe**\n"
            f"Lvl: `{user['level']}`\n"
            f"EXP: `{user['exp']}`\n"
            f"{exp_info_line(user)}\n\n"
            "**⚔️ Walka**\n"
            f"Atak: `{user['attack']} (+{atk_bonus} ekwip.)`\n"
            f"Obrona: `{user['defense']} (+{def_bonus} ekwip.)`\n"
            f"Razem atak: `{user['attack'] + atk_bonus}`\n"
            f"Razem obrona: `{user['defense'] + def_bonus}`\n\n"
            "**❤️ Zdrowie**\n"
            f"{hp_bar}\n"
            f"`{user['hp']}/{user['max_hp']} HP`\n"
            "HP odnawia się o `1` punkt co `2 min`.\n\n"
            "**⚡ Stamina**\n"
            f"{stamina_bar}\n"
            f"`{user['stamina']}/{user['max_stamina']}`\n\n"
            "**💰 Zasoby**\n"
            f"Złoto: `{user['gold']}`\n"
            f"Grzybki: `{user['mushrooms']}`\n\n"
            "Spróbuj `/tavern`, aby kontynuować przygodę."
        )
        await interaction.response.send_message(view=message_view(text, 0x3498DB))

    @app_commands.command(name="leaderboard", description="Top 10 graczy")
    async def leaderboard(self, interaction: discord.Interaction):
        users = await get_leaderboard(10)
        if not users:
            text = "### 🏆 Ranking\nBrak graczy."
        else:
            rows = ["### 🏆 Ranking"]
            for i, user in enumerate(users, 1):
                rows.append(f"**{i}.** `{user['discord_id']}` | Lvl `{user['level']}` | EXP `{user['exp']}` | Gold `{user['gold']}` | 🍄 `{user['mushrooms']}`")
            text = "\n".join(rows)

        await interaction.response.send_message(view=message_view(text, 0xF1C40F))


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
