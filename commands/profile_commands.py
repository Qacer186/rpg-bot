import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_user, get_equipped_bonuses, get_leaderboard


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def create_progress_bar(current, maximum, length=10):
        filled = int(length * current / maximum)
        return "🟩" * filled + "⬜" * (length - filled)

    @app_commands.command(name="profile", description="Pokazuje profil gracza")
    async def profile(self, interaction: discord.Interaction):
        user = await get_user(str(interaction.user.id))
        if not user:
            await interaction.response.send_message("Użyj /start!", ephemeral=True)
            return

        bonuses = await get_equipped_bonuses(str(interaction.user.id))
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        hp_bar = self.create_progress_bar(user['hp'], user['max_hp'], 15)
        stamina_bar = self.create_progress_bar(user['stamina'], 100, 15)

        embed = discord.Embed(
            title=f"👤 PROFIL: {interaction.user.name}",
            description="═══════════════════════════════════════",
            color=0x3498db
        )
        embed.add_field(
            name="🎯 PODSTAWOWE",
            value=f"**Lvl:** {user['level']}\n"
                  f"**EXP:** {user['exp']}",
            inline=False
        )
        embed.add_field(
            name="⚔️ WALKA",
            value=f"**Atak:** {user['attack']} (+{atk_bonus} ekwip.)\n"
                  f"**Obrona:** {user['defense']} (+{def_bonus} ekwip.)\n"
                  f"**Razem Atak:** {user['attack'] + atk_bonus}\n"
                  f"**Razem Obrona:** {user['defense'] + def_bonus}",
            inline=False
        )
        embed.add_field(name="❤️ ZDROWIE", value=f"{hp_bar}\n`{user['hp']}/{user['max_hp']} HP`", inline=False)
        embed.add_field(name="⚡ STAMINA", value=f"{stamina_bar}\n`{user['stamina']}/100`", inline=False)
        embed.add_field(name="💰 ZASOBY", value=f"**Złota:** {user['gold']}\n**Doświadczenie:** {user['exp']}", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Spróbuj /tavern aby kontynuować przygodę!")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Top 10 graczy")
    async def leaderboard(self, interaction: discord.Interaction):
        users = await get_leaderboard(10)
        embed = discord.Embed(title="🏆 Ranking", color=0xffd700)
        if not users:
            embed.description = "Brak graczy"
        else:
            for i, user in enumerate(users, 1):
                embed.add_field(
                    name=f"{i}. {user['discord_id']}",
                    value=f"Lvl {user['level']} | EXP: {user['exp']} | Gold: {user['gold']}",
                    inline=False
                )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
