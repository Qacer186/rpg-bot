import asyncio
import math
import time

import discord
from discord import ui

from database.db import (
    get_random_quests,
    get_user,
    exp_info_line,
    regenerate_stamina,
    update_user,
    update_user_after_fight,
)
from services.rabbitmq import send_to_queue
from utils.containers import add_action_row, add_container, message_view
from utils.security import ensure_view_owner
from views.fight_view import FightView


def create_progress_bar(current, maximum, length=10):
    if maximum <= 0:
        return "⬜" * length
    filled = int(length * current / maximum)
    filled = max(0, min(length, filled))
    return "🟩" * filled + "⬜" * (length - filled)


def format_quest_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes > 0:
        return f"{minutes} min {sec} sek"
    return f"{sec} sek"


def quest_progress_values(start_time: float, duration_sec: int):
    if duration_sec <= 0:
        return 0, 10, 100

    elapsed = time.time() - start_time
    elapsed = max(0, min(duration_sec, elapsed))
    remaining = max(0, math.ceil(duration_sec - elapsed))
    progress = int((elapsed / duration_sec) * 10)
    progress = max(0, min(10, progress))
    percent = int((elapsed / duration_sec) * 100)
    percent = max(0, min(100, percent))

    if remaining == 0:
        progress = 10
        percent = 100

    return remaining, progress, percent


def build_tavern_text(user, quests, footer=None):
    hp_bar = create_progress_bar(user['hp'], user['max_hp'], 15)
    stamina_bar = create_progress_bar(user['stamina'], user['max_stamina'], 15)

    rows = [
        "### 🍻 KARCZMA U PODPITEGO GOBLINA",
        "━━━━━━━━━━━━━━━━━━━━",
        "**⚔️ Statystyki**",
        f"Lvl: `{user['level']}` | EXP: `{user['exp']}`",
        exp_info_line(user),
        f"Atak: `{user['attack']}` | Obrona: `{user['defense']}`",
        "",
        "**❤️ Zdrowie**",
        hp_bar,
        f"`{user['hp']}/{user['max_hp']} HP`",
        "HP odnawia się o 1 punkt co 2 min.",
        "",
        "**⚡ Stamina**",
        stamina_bar,
        f"`{user['stamina']}/{user['max_stamina']}`",
        "",
        "**💰 Portfel**",
        f"`{user['gold']} złota`",
        f"🍄 `{user['mushrooms']} grzybków`",
        "",
        "**📜 Dostępne misje**",
        "Misje są ułożone od najtrudniejszej do najłatwiejszej.",
        "Odświeżenie misji: `/refresh_missions` za 1 grzybka."
    ]

    if not quests:
        rows.append("Nie udało się pobrać misji.")
    else:
        for i, quest in enumerate(quests, 1):
            difficulty = quest.get('difficulty_label', '📜 MISJA')
            fight_info = "⚔️ Walka: `tak`" if quest.get('requires_combat', True) else "✅ Walka: `nie, 100% wygranej`"

            rows.append(
                f"\n**Misja {i}: {quest['name']}**\n"
                f"{difficulty}\n"
                f"⏱️ Czas: `{quest['duration']} min`\n"
                f"{fight_info}\n"
                f"💰 Złoto: `{quest['gold']}`\n"
                f"✨ EXP: `{quest['exp']}`"
            )

    if footer:
        rows.append(f"\n{footer}")

    return "\n".join(rows)


class QuestProgressView(discord.ui.LayoutView):
    def __init__(self, quest, start_time, duration_sec, user_data, bot):
        super().__init__(timeout=None)
        self.quest = quest
        self.start_time = start_time
        self.duration_sec = duration_sec
        self.end_time = start_time + duration_sec
        self.user_data = user_data
        self.bot = bot
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = add_container(self, self.get_timestamp_text(), 0x6B4226)
        cancel_btn = ui.Button(label="🛑 Anuluj misję", style=discord.ButtonStyle.danger)
        cancel_btn.callback = self.cancel_quest
        add_action_row(container, cancel_btn)

    async def cancel_quest(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_data['discord_id'], "/tavern"):
            return

        await interaction.response.defer()

        current_user = await get_user(self.user_data['discord_id'])
        if not current_user or not current_user['on_expedition']:
            await interaction.followup.send(view=message_view("⚠️ Ta misja jest już zakończona albo anulowana.", 0xE67E22), ephemeral=True)
            return

        if current_user:
            await update_user_after_fight(
                self.user_data['discord_id'],
                current_user['hp'],
                current_user['exp'],
                0,
                max(0, current_user['stamina'] - 5)
            )
            await update_user(
                self.user_data['discord_id'],
                on_expedition=0,
                expedition_start_time=0,
                expedition_duration=0
            )

        text = (
            "### ❌ Misja anulowana\n"
            f"Opuściłeś misję: **{self.quest['name']}**\n\n"
            "💔 Kara: `-5 staminy`"
        )
        await interaction.message.edit(view=message_view(text, 0xE74C3C))

    def get_timestamp_text(self):
        remaining, progress, percent = quest_progress_values(self.start_time, self.duration_sec)
        bar = "█" * progress + "░" * (10 - progress)
        is_easy = not self.quest.get('requires_combat', True)
        title = "### 📦 Misja czasowa w toku" if is_easy else "### ⚔️ Misja w toku"
        fight_info = "✅ Bez walki, 100% wygranej" if is_easy else "⚔️ Po czasie rozpocznie się walka"

        if remaining == 0:
            time_text = "⏱️ Pozostało: `0 sek`\n⌛ Misja dobiegła końca. Wynik pojawi się za chwilę."
        else:
            time_text = f"⏱️ Pozostało: `{format_quest_time(remaining)}`"

        return (
            f"{title}\n"
            f"📍 Cel: **{self.quest['name']}**\n"
            f"{self.quest.get('difficulty_label', '📜 MISJA')}\n"
            f"{fight_info}\n"
            f"{time_text}\n\n"
            f"📊 Postęp: `[{bar}]` `{percent}%`\n\n"
            f"💰 Nagroda: `{self.quest['gold']} złota`\n"
            f"✨ Doświadczenie: `{self.quest['exp']} EXP`"
        )


class QuestView(discord.ui.LayoutView):
    def __init__(self, user_data, quests, bot, footer=None):
        super().__init__(timeout=None)
        self.user_data = user_data
        self.quests = quests
        self.bot = bot
        self.footer = footer
        self.locked = False
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = add_container(self, build_tavern_text(self.user_data, self.quests, self.footer), 0x6B4226)
        self.setup_quest_select(container)

    def setup_quest_select(self, container):
        if not self.quests:
            return

        select = ui.Select(
            placeholder="🎯 Wybierz misję...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"Misja {i + 1}: {quest['name'][:80]}",
                    description=(
                        f"{quest.get('difficulty_label', '📜')} | "
                        f"⏱️ {quest['duration']}m | 💰 {quest['gold']} | ✨ {quest['exp']}"
                    )[:100],
                    value=str(i),
                    emoji="✅" if not quest.get('requires_combat', True) else "⚔️"
                )
                for i, quest in enumerate(self.quests)
            ]
        )
        select.callback = self.on_quest_select
        add_action_row(container, select)

    async def on_quest_select(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_data['discord_id'], "/tavern"):
            return

        current_user = await get_user(self.user_data['discord_id'])
        if not current_user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if current_user['on_expedition']:
            await interaction.response.send_message(view=message_view("⚠️ Masz już aktywną misję. Najpierw ją zakończ albo anuluj.", 0xE67E22), ephemeral=True)
            return

        if self.locked:
            await interaction.response.send_message(view=message_view("⚠️ Ta wiadomość ma już wybraną misję. Użyj `/tavern`, żeby otworzyć nową karczmę.", 0xE67E22), ephemeral=True)
            return

        self.locked = True
        await interaction.response.defer()

        quest_idx = int(interaction.data['values'][0])
        quest = self.quests[quest_idx]

        quest_data = {
            "user_id": self.user_data['discord_id'],
            "monster_name": quest['name'],
            "duration_minutes": quest['duration'],
            "gold_reward": quest['gold'],
            "exp_reward": quest['exp'],
            "difficulty": quest.get('difficulty', 'unknown'),
            "requires_combat": quest.get('requires_combat', True),
            "action": "start_quest"
        }

        start_time = time.time()
        await update_user(
            self.user_data['discord_id'],
            on_expedition=1,
            expedition_start_time=start_time,
            expedition_duration=quest['duration']
        )

        try:
            send_to_queue('quest_selections', quest_data)
        except Exception as e:
            print(f"[RABBITMQ ERROR] {e}")

        duration_sec = quest['duration'] * 60
        progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
        await interaction.message.edit(view=progress_view)

        self.bot.loop.create_task(self.update_quest_progress(interaction.message, quest, start_time, duration_sec))

    async def update_quest_progress(self, message, quest, start_time, duration_sec):
        try:
            end_time = start_time + duration_sec
            last_rendered_second = None

            while True:
                current_user = await get_user(self.user_data['discord_id'])
                if not current_user or not current_user['on_expedition']:
                    break

                remaining_float = end_time - time.time()
                remaining_seconds = max(0, math.ceil(remaining_float))

                should_render = (
                    remaining_seconds != last_rendered_second
                    and (remaining_seconds <= 30 or remaining_seconds % 5 == 0)
                )

                if should_render:
                    progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
                    await message.edit(view=progress_view)
                    last_rendered_second = remaining_seconds

                if remaining_float <= 0:
                    progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
                    await message.edit(view=progress_view)
                    await asyncio.sleep(2)

                    current_user = await get_user(self.user_data['discord_id'])
                    if not current_user or not current_user['on_expedition']:
                        break

                    if not quest.get('requires_combat', True):
                        await self.finish_easy_quest(message, quest)
                        break

                    await regenerate_stamina(self.user_data['discord_id'])
                    fresh_user = await get_user(self.user_data['discord_id'])
                    fight_view = FightView(
                        fresh_user,
                        quest['monster'],
                        on_win=self.return_to_tavern,
                        on_lose=self.return_to_tavern,
                        gold_reward=quest['gold'],
                        exp_reward=quest['exp']
                    )
                    await message.edit(view=fight_view)
                    break

                await asyncio.sleep(1)
        except Exception as e:
            print(f"[QUEST ERROR] {e}")
            try:
                current_user = await get_user(self.user_data['discord_id'])
                if not current_user or not current_user['on_expedition']:
                    return

                if not quest.get('requires_combat', True):
                    await self.finish_easy_quest(message, quest)
                    return

                await regenerate_stamina(self.user_data['discord_id'])
                fresh_user = await get_user(self.user_data['discord_id'])
                fight_view = FightView(
                    fresh_user,
                    quest['monster'],
                    on_win=self.return_to_tavern,
                    on_lose=self.return_to_tavern,
                    gold_reward=quest['gold'],
                    exp_reward=quest['exp']
                )
                await message.edit(view=fight_view)
            except Exception:
                pass

    async def finish_easy_quest(self, message, quest):
        current_user = await get_user(self.user_data['discord_id'])
        if not current_user:
            return

        await update_user_after_fight(
            self.user_data['discord_id'],
            current_user['hp'],
            current_user['exp'] + quest['exp'],
            quest['gold'],
            max(0, current_user['stamina'] - 5)
        )
        await update_user(
            self.user_data['discord_id'],
            on_expedition=0,
            expedition_start_time=0,
            expedition_duration=0
        )

        fresh_user = await get_user(self.user_data['discord_id'])
        await regenerate_stamina(fresh_user['discord_id'])
        fresh_user = await get_user(fresh_user['discord_id'])
        quests = await get_random_quests(fresh_user['discord_id'])

        footer = (
            "### ✅ Misja łatwa zakończona sukcesem\n"
            f"Wykonano zadanie: **{quest['name']}**\n\n"
            "Nie było walki z potworem, dlatego misja zakończyła się pewną wygraną.\n\n"
            f"💰 Złoto: `+{quest['gold']}`\n"
            f"✨ Doświadczenie: `+{quest['exp']} EXP`\n"
            f"{exp_info_line(fresh_user)}\n"
            "⚡ Stamina: `-5`\n\n"
            "Wróciłeś do karczmy. Poniżej są nowe misje."
        )

        quest_view = QuestView(fresh_user, quests, self.bot, footer=footer)
        await message.edit(view=quest_view)

    async def return_to_tavern(self, interaction):
        user = await get_user(self.user_data['discord_id'])
        await update_user(
            self.user_data['discord_id'],
            on_expedition=0,
            expedition_start_time=0,
            expedition_duration=0
        )
        await regenerate_stamina(user['discord_id'])
        user = await get_user(user['discord_id'])

        quests = await get_random_quests(user['discord_id'])
        quest_view = QuestView(user, quests, self.bot, footer="Powróciłeś do karczmy! Powodzenia, bohaterze!")
        await interaction.followup.edit_message(interaction.message.id, view=quest_view)
