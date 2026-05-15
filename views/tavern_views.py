import discord
from discord import ui
import time
from database.db import update_user_after_fight, get_user, get_random_quests, regenerate_stamina
from views.fight_view import FightView
from services.rabbitmq import send_to_queue


def create_progress_bar(current, maximum, length=10):
    filled = int(length * current / maximum)
    return "🟩" * filled + "⬜" * (length - filled)


class QuestProgressView(discord.ui.View):
    def __init__(self, quest, start_time, duration_sec, user_data, bot):
        super().__init__(timeout=None)
        self.quest = quest
        self.start_time = start_time
        self.duration_sec = duration_sec
        self.end_time = start_time + duration_sec
        self.user_data = user_data
        self.bot = bot

    @ui.button(label="🛑 Anuluj misję", style=discord.ButtonStyle.danger)
    async def cancel_quest(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        embed = discord.Embed(
            title="❌ Misja anulowana",
            description=f"Opuściłeś misję: **{self.quest['name']}**",
            color=0xe74c3c
        )
        embed.add_field(name="💔 Kara", value="Strata 5 staminy", inline=True)

        await update_user_after_fight(
            self.user_data['discord_id'],
            self.user_data['hp'],
            self.user_data['exp'],
            0,
            max(0, self.user_data['stamina'] - 5)
        )

        await interaction.message.edit(embed=embed, view=None)

    def get_timestamp_embed(self):
        elapsed = time.time() - self.start_time
        remaining = self.duration_sec - elapsed

        embed = discord.Embed(title="⚔️ Misja w toku", color=0x6b4226)
        end_unix = int(self.end_time)
        timestamp = f"<t:{end_unix}:R>"

        embed.add_field(name="📍 Cel", value=f"**{self.quest['name']}**", inline=False)
        embed.add_field(name="⏱️ Koniec", value=timestamp, inline=True)

        if remaining > 0:
            progress = int((elapsed / self.duration_sec) * 10)
            bar = "█" * progress + "░" * (10 - progress)
            percent = int((elapsed / self.duration_sec) * 100)
            embed.add_field(name="📊 Postęp", value=f"`[{bar}]` {percent}%", inline=False)
        else:
            embed.add_field(name="📊 Postęp", value="`[██████████]` 100%", inline=False)

        embed.add_field(name="💰 Nagroda", value=f"{self.quest['gold']} złota", inline=True)
        embed.add_field(name="✨ Doświadczenie", value=f"{self.quest['exp']} EXP", inline=True)

        return embed


class QuestView(discord.ui.View):
    def __init__(self, user_data, quests, bot):
        super().__init__(timeout=None)
        self.user_data = user_data
        self.quests = quests
        self.bot = bot
        self.setup_quest_select()

    def setup_quest_select(self):
        self.clear_items()
        select = ui.Select(
            placeholder="🎯 Wybierz misję...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"Misja {i + 1}: {quest['name']}",
                    description=f"⏱️ {quest['duration']}m | 💰 {quest['gold']} | ✨ {quest['exp']}",
                    value=str(i),
                    emoji="⚔️"
                )
                for i, quest in enumerate(self.quests)
            ]
        )
        select.callback = self.on_quest_select
        self.add_item(select)

    async def on_quest_select(self, interaction: discord.Interaction):
        await interaction.response.defer()

        quest_idx = int(interaction.data['values'][0])
        quest = self.quests[quest_idx]

        quest_data = {
            "user_id": self.user_data['discord_id'],
            "monster_name": quest['name'],
            "duration_minutes": quest['duration'],
            "gold_reward": quest['gold'],
            "exp_reward": quest['exp'],
            "action": "start_quest"
        }
        send_to_queue('quest_selections', quest_data)

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        start_time = time.time()
        duration_sec = quest['duration'] * 60
        progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
        progress_embed = progress_view.get_timestamp_embed()
        await interaction.message.edit(embed=progress_embed, view=progress_view)

        self.bot.loop.create_task(self.update_quest_progress(interaction.message, quest, start_time, duration_sec))

    async def update_quest_progress(self, message, quest, start_time, duration_sec):
        try:
            while True:
                elapsed = time.time() - start_time
                remaining = duration_sec - elapsed

                if remaining <= 0:
                    fight_view = FightView(
                        self.user_data,
                        quest['monster'],
                        on_win=self.return_to_tavern,
                        on_lose=self.return_to_tavern,
                        gold_reward=quest['gold'],
                        exp_reward=quest['exp']
                    )
                    embed = discord.Embed(
                        title="⚔️ Natrafiłeś na potwora!",
                        description=f"Przed tobą stanął **{quest['monster']['name']}**!",
                        color=0xe74c3c
                    )
                    embed.add_field(name="⚔️ Atak", value=str(quest['monster']['attack']), inline=True)
                    embed.add_field(name="🛡️ Obrona", value=str(quest['monster']['defense']), inline=True)
                    embed.add_field(name="❤️ HP", value=f"{quest['monster']['hp']} HP", inline=True)
                    await message.edit(embed=embed, view=fight_view)
                    break

                if int(elapsed) % 10 < 2 or remaining < 30:
                    progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
                    progress_embed = progress_view.get_timestamp_embed()
                    await message.edit(embed=progress_embed, view=progress_view)

                await asyncio.sleep(2)
        except Exception as e:
            print(f"[QUEST ERROR] {e}")
            try:
                fight_view = FightView(
                    self.user_data,
                    quest['monster'],
                    on_win=self.return_to_tavern,
                    on_lose=self.return_to_tavern,
                    gold_reward=quest['gold'],
                    exp_reward=quest['exp']
                )
                embed = discord.Embed(
                    title="⚔️ Natrafiłeś na potwora!",
                    description=f"Przed tobą stanął **{quest['monster']['name']}**!",
                    color=0xe74c3c
                )
                await message.edit(embed=embed, view=fight_view)
            except Exception:
                pass

    async def return_to_tavern(self, interaction):
        user = await get_user(self.user_data['discord_id'])
        await regenerate_stamina(user['discord_id'])
        user = await get_user(user['discord_id'])

        quests = await get_random_quests(user['discord_id'])
        quest_view = QuestView(user, quests, self.bot)

        hp_bar = create_progress_bar(user['hp'], user['max_hp'], 15)
        stamina_bar = create_progress_bar(user['stamina'], 100, 15)

        embed = discord.Embed(
            title="🍻 KARCZMA U PODPITEGO GOBLINA",
            description="═══════════════════════════════════════",
            color=0x6b4226
        )
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
        embed.add_field(name="📜 DOSTĘPNE MISJE", value="", inline=False)

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

        embed.set_footer(text="Powróciłeś do karczmy! Powodzenia, bohaterze!")
        await interaction.response.edit_message(embed=embed, view=quest_view)
