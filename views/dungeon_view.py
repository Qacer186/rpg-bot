import asyncio

import discord
from discord import ui

from database.db import (
    complete_dungeon_monster,
    get_current_dungeon_monster_from_user,
    get_dungeon_cooldown_seconds,
    get_dungeon_monsters,
    get_user,
    regenerate_stamina,
    start_dungeon_attack,
)
from utils.containers import add_action_row, add_container, message_view
from utils.security import ensure_view_owner
from views.fight_view import FightView


def _format_time(seconds: int):
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes} min {sec} sek"


def build_dungeon_text(user, footer=None):
    monsters = get_dungeon_monsters()
    monster = get_current_dungeon_monster_from_user(user)
    progress = int(user['dungeon_progress'] or 0) + 1
    cooldown = get_dungeon_cooldown_seconds(user)

    if cooldown > 0:
        cooldown_text = f"⏳ Następny darmowy atak za: `{_format_time(cooldown)}`"
    else:
        cooldown_text = "✅ Możesz teraz zaatakować loch."

    rows = [
        "### 🏰 LOCHY",
        "Stały loch ma kilku przeciwników. Każdy ma swój stały poziom i statystyki.",
        "Po pokonaniu ostatniego przeciwnika dostajesz specjalny przedmiot z lochu.",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Etap: `{progress}/{len(monsters)}`",
        f"❤️ HP: `{user['hp']}/{user['max_hp']}`",
        "HP odnawia się o `1` punkt co `2 min`.",
        f"🍄 Grzybki: `{user['mushrooms']}`",
        cooldown_text,
        "Czas lochu odświeża się automatycznie co około `15 sek`.",
        "",
        "**Aktualny przeciwnik**",
        f"👹 {monster['name']}",
        f"Lvl: `{monster['level']}`",
        f"❤️ HP: `{monster['hp']}`",
        f"⚔️ Atak: `{monster['attack']}`",
        f"🛡️ Obrona: `{monster['defense']}`",
        f"💰 Nagroda: `{monster['gold']}` złota",
        f"✨ EXP: `{monster['exp']}`",
        "",
        "Darmowy atak jest raz na 30 minut. Grzybek omija czekanie."
    ]

    if footer:
        rows.append(f"\n{footer}")

    return "\n".join(rows)


class DungeonView(discord.ui.LayoutView):
    def __init__(self, user_id: str, bot, footer=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bot = bot
        self.footer = footer
        self.message = None
        self.auto_refresh_task = None

    async def reload(self):
        await regenerate_stamina(self.user_id)
        self.clear_items()
        user = await get_user(self.user_id)
        container = add_container(self, build_dungeon_text(user, self.footer), 0x5D3FD3)
        self.setup_buttons(container)

    def setup_buttons(self, container):
        attack_btn = ui.Button(label="⚔️ Atakuj loch", style=discord.ButtonStyle.danger)
        attack_btn.callback = lambda interaction: self.start_attack(interaction, False)

        mushroom_btn = ui.Button(label="🍄 Atak za grzybka", style=discord.ButtonStyle.success)
        mushroom_btn.callback = lambda interaction: self.start_attack(interaction, True)

        refresh_btn = ui.Button(label="🔄 Odśwież czas", style=discord.ButtonStyle.secondary)
        refresh_btn.callback = self.refresh_view

        add_action_row(container, attack_btn, mushroom_btn, refresh_btn)

    def start_auto_refresh(self, message):
        self.message = message
        self.stop_auto_refresh()
        self.auto_refresh_task = self.bot.loop.create_task(self.auto_refresh_loop())

    def stop_auto_refresh(self):
        if self.auto_refresh_task and not self.auto_refresh_task.done():
            self.auto_refresh_task.cancel()
        self.auto_refresh_task = None

    async def auto_refresh_loop(self):
        try:
            while True:
                await asyncio.sleep(15)
                user = await get_user(self.user_id)
                if not user or not self.message:
                    break

                await self.reload()
                await self.message.edit(view=self)

                if get_dungeon_cooldown_seconds(user) <= 0:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[DUNGEON TIMER ERROR] {e}")

    async def refresh_view(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/dungeon"):
            return

        await interaction.response.defer()
        await self.reload()
        await interaction.message.edit(view=self)
        self.start_auto_refresh(interaction.message)

    async def start_attack(self, interaction: discord.Interaction, use_mushroom: bool):
        if not await ensure_view_owner(interaction, self.user_id, "/dungeon"):
            return

        self.stop_auto_refresh()
        await interaction.response.defer()
        await regenerate_stamina(self.user_id)
        user = await get_user(self.user_id)

        if not user:
            await interaction.followup.send(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if user['stamina'] < 10:
            await interaction.followup.send(view=message_view("⚡ Masz za mało staminy na walkę w lochu.", 0xE67E22), ephemeral=True)
            return

        ok, message, monster = await start_dungeon_attack(self.user_id, use_mushroom)
        if not ok:
            await interaction.followup.send(view=message_view(f"⚠️ {message}", 0xE67E22), ephemeral=True)
            await self.reload()
            await interaction.message.edit(view=self)
            self.start_auto_refresh(interaction.message)
            return

        fresh_user = await get_user(self.user_id)
        fight_view = FightView(
            fresh_user,
            monster,
            on_win=self.on_dungeon_win,
            on_lose=self.on_dungeon_lose,
            gold_reward=monster['gold'],
            exp_reward=monster['exp']
        )
        await interaction.message.edit(view=fight_view)

    async def on_dungeon_win(self, interaction: discord.Interaction):
        result = await complete_dungeon_monster(self.user_id)
        new_view = DungeonView(self.user_id, self.bot, footer=result)
        await new_view.reload()
        await interaction.followup.edit_message(interaction.message.id, view=new_view)
        new_view.start_auto_refresh(interaction.message)

    async def on_dungeon_lose(self, interaction: discord.Interaction):
        new_view = DungeonView(
            self.user_id,
            self.bot,
            footer="### 💀 Przegrana w lochu\nNie przechodzisz dalej. Kolejna próba będzie po 30 minutach albo za grzybka."
        )
        await new_view.reload()
        await interaction.followup.edit_message(interaction.message.id, view=new_view)
        new_view.start_auto_refresh(interaction.message)
