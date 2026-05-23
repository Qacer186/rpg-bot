import asyncio
import math
import time

import discord
from discord import ui

from database.db import (
    buy_item,
    complete_dungeon_monster,
    get_current_dungeon_monster_from_user,
    get_dungeon_cooldown_seconds,
    get_equipped_bonuses,
    get_item_by_id,
    get_potion_items,
    get_random_quests,
    get_shop_items_for_user,
    get_user,
    get_user_inventory,
    exp_info_line,
    regenerate_stamina,
    refresh_user_quests,
    refresh_user_shop,
    start_dungeon_attack,
    update_user,
    update_user_after_fight,
)
from services.rabbitmq import send_to_queue
from utils.containers import add_action_row, add_container, message_view
from utils.security import ensure_view_owner
from views.fight_view import FightView


ERROR_COLOR = 0xE74C3C
SUCCESS_COLOR = 0x2ECC71
WARNING_COLOR = 0xE67E22
SHOP_COLOR = 0xF1C40F
POTION_COLOR = 0x9B59B6
TAVERN_COLOR = 0x6B4226
DUNGEON_COLOR = 0x5D3FD3
BASE_COLOR = 0x8B4513
SHOP_OFFER_SIZE = 5


def _chunk(items, size=5):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _format_time(seconds: int):
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes} min {sec} sek"


def _format_quest_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes > 0:
        return f"{minutes} min {sec} sek"
    return f"{sec} sek"


def _quest_progress_values(start_time: float, duration_sec: int):
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


def _equipment_line(index: int, item):
    parts = []
    if item['atk_bonus']:
        parts.append(f"⚔️ +{item['atk_bonus']}")
    if item['def_bonus']:
        parts.append(f"🛡️ +{item['def_bonus']}")
    bonus = " | ".join(parts) if parts else "brak bonusu"
    return (
        f"**{index}. {item['name']}**\n"
        f"Cena: `{item['price']}` złota | Lvl: `{item['level_required']}` | {bonus}"
    )


def _potion_line(index: int, item):
    effect = {
        "heal": f"leczy `{item['effect_value']}` HP",
        "full_heal": "leczy do pełna",
        "stamina": f"odnawia `{item['effect_value']}` staminy",
        "attack": f"dodaje `+{item['effect_value']}` ataku",
        "defense": f"dodaje `+{item['effect_value']}` obrony",
        "max_hp": f"dodaje `+{item['effect_value']}` max HP",
    }.get(item['effect_type'], "specjalne działanie")

    return (
        f"**{index}. {item['name']}**\n"
        f"Cena: `{item['price']}` złota | Lvl: `{item['level_required']}` | {effect}"
    )


async def _send_private(interaction: discord.Interaction, text: str, color: int = ERROR_COLOR):
    view = message_view(text, color)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


class GameScreenView(discord.ui.LayoutView):
    def __init__(self, user_id: str, bot, current_tab: str = "character", footer: str | None = None):
        super().__init__(timeout=None)
        self.user_id = str(user_id)
        self.bot = bot
        self.current_tab = current_tab
        self.footer = footer
        self.user = None
        self.quests = []
        self.shop_items = []
        self.potion_items = []
        self.locked = False

    async def reload(self):
        self.clear_items()
        text = await self.get_tab_text()
        container = add_container(self, text, self.get_tab_color())
        self.setup_context_buttons(container)
        self.setup_navigation_buttons(container)

    def get_tab_color(self):
        colors = {
            "character": BASE_COLOR,
            "inventory": BASE_COLOR,
            "shop": SHOP_COLOR,
            "tavern": TAVERN_COLOR,
            "dungeon": DUNGEON_COLOR,
            "potions": POTION_COLOR,
        }
        return colors.get(self.current_tab, 0x5865F2)

    def setup_navigation_buttons(self, container):
        main_tabs = [
            ("character", "👤 POSTAĆ"),
            ("inventory", "🎒 EKWIPUNEK"),
            ("shop", "🛒 SKLEP"),
            ("potions", "🧪 POTKI"),
        ]

        tab_buttons = []
        for tab, label in main_tabs:
            style = discord.ButtonStyle.primary if self.current_tab == tab else discord.ButtonStyle.gray
            button = ui.Button(label=label, style=style)
            button.callback = lambda interaction, selected_tab=tab: self.switch_tab(interaction, selected_tab)
            tab_buttons.append(button)

        add_action_row(container, *tab_buttons)

        action_buttons = []
        action_tabs = [
            ("tavern", "🍻 KARCZMA", discord.ButtonStyle.success),
            ("dungeon", "🏰 LOCH", discord.ButtonStyle.danger),
        ]

        for tab, label, style in action_tabs:
            button = ui.Button(label=label, style=style)
            button.callback = lambda interaction, selected_tab=tab: self.switch_tab(interaction, selected_tab)
            action_buttons.append(button)

        add_action_row(container, *action_buttons, separator=False)

    def setup_context_buttons(self, container):
        if not self.user:
            return

        if self.current_tab == "tavern":
            self.setup_tavern_buttons(container)
        elif self.current_tab == "shop":
            self.setup_shop_buttons(container)
        elif self.current_tab == "potions":
            self.setup_potion_buttons(container)
        elif self.current_tab == "dungeon":
            self.setup_dungeon_buttons(container)

    def setup_tavern_buttons(self, container):
        if self.quests:
            select = ui.Select(
                placeholder="🎯 Wybierz misję z karczmy...",
                min_values=1,
                max_values=1,
                disabled=bool(self.user['on_expedition'] or self.user['stamina'] < 10),
                options=[
                    discord.SelectOption(
                        label=f"Misja {index + 1}: {quest['name'][:80]}",
                        description=(
                            f"{quest.get('difficulty_label', '📜')} | "
                            f"⏱️ {quest['duration']}m | 💰 {quest['gold']} | ✨ {quest['exp']}"
                        )[:100],
                        value=str(index),
                        emoji="✅" if not quest.get('requires_combat', True) else "⚔️"
                    )
                    for index, quest in enumerate(self.quests)
                ]
            )
            select.callback = self.select_quest_from_game
            add_action_row(container, select)

        refresh_button = ui.Button(
            label="🍄 Odśwież misje",
            style=discord.ButtonStyle.success,
            disabled=self.user['mushrooms'] < 1,
        )
        refresh_button.callback = self.refresh_quests_from_game
        add_action_row(container, refresh_button, separator=False)

    def setup_shop_buttons(self, container):
        buy_buttons = []
        for index, item in enumerate(self.shop_items, start=1):
            button = ui.Button(
                label=f"Kup {index}",
                style=discord.ButtonStyle.primary,
                disabled=self.user['gold'] < item['price'] or self.user['level'] < item['level_required'],
            )
            button.callback = lambda interaction, item_id=item['id']: self.buy_shop_item_from_game(interaction, item_id)
            buy_buttons.append(button)

        if buy_buttons:
            add_action_row(container, *buy_buttons)

        refresh_button = ui.Button(
            label="🍄 Odśwież sklep",
            style=discord.ButtonStyle.success,
            disabled=self.user['mushrooms'] < 1,
        )
        refresh_button.callback = self.refresh_shop_from_game
        add_action_row(container, refresh_button, separator=not bool(buy_buttons))

    def setup_potion_buttons(self, container):
        buy_buttons = []
        for index, item in enumerate(self.potion_items, start=1):
            button = ui.Button(
                label=f"Kup {index}",
                style=discord.ButtonStyle.primary,
                disabled=self.user['gold'] < item['price'] or self.user['level'] < item['level_required'],
            )
            button.callback = lambda interaction, item_id=item['id']: self.buy_potion_from_game(interaction, item_id)
            buy_buttons.append(button)

        for row_buttons in _chunk(buy_buttons, 5):
            add_action_row(container, *row_buttons)

    def setup_dungeon_buttons(self, container):
        cooldown = get_dungeon_cooldown_seconds(self.user)

        attack_button = ui.Button(
            label="⚔️ Atakuj loch",
            style=discord.ButtonStyle.danger,
            disabled=cooldown > 0 or self.user['stamina'] < 10,
        )
        attack_button.callback = lambda interaction: self.start_dungeon_from_game(interaction, False)

        mushroom_button = ui.Button(
            label="🍄 Atak za grzybka",
            style=discord.ButtonStyle.success,
            disabled=self.user['mushrooms'] < 1 or self.user['stamina'] < 10,
        )
        mushroom_button.callback = lambda interaction: self.start_dungeon_from_game(interaction, True)

        refresh_button = ui.Button(label="🔄 Odśwież czas", style=discord.ButtonStyle.secondary)
        refresh_button.callback = self.refresh_current_tab

        add_action_row(container, attack_button, mushroom_button, refresh_button)

    async def switch_tab(self, interaction: discord.Interaction, new_tab: str):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        self.current_tab = new_tab
        self.footer = None
        self.locked = False
        await self.reload()
        await interaction.message.edit(view=self)

    async def refresh_current_tab(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        await self.reload()
        await interaction.message.edit(view=self)

    async def get_tab_text(self):
        await regenerate_stamina(self.user_id)
        self.user = await get_user(self.user_id)
        self.quests = []
        self.shop_items = []
        self.potion_items = []

        if not self.user:
            return "❌ Najpierw użyj `/start`."

        if self.current_tab == "character":
            return await self.build_character_tab(self.user)
        if self.current_tab == "inventory":
            return await self.build_inventory_tab(self.user)
        if self.current_tab == "shop":
            return await self.build_shop_tab(self.user)
        if self.current_tab == "potions":
            return await self.build_potions_tab(self.user)
        if self.current_tab == "tavern":
            return await self.build_tavern_tab(self.user)
        if self.current_tab == "dungeon":
            return await self.build_dungeon_tab(self.user)

        return "### Błąd\nNieznany ekran."

    async def build_character_tab(self, user):
        bonuses = await get_equipped_bonuses(self.user_id)
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        hp_bar = self.create_bar(user['hp'], user['max_hp'], 20, "█", "░")
        stamina_bar = self.create_bar(user['stamina'], user['max_stamina'], 20, "▓", "░")

        rows = [
            "### ⚔️ POSTAĆ",
            "━━━━━━━━━━━━━━━━━━━━",
            "**📊 Główne**",
            f"Lvl: `{user['level']}`",
            f"EXP: `{user['exp']}`",
            exp_info_line(user),
            "",
            "**⚔️ Walka**",
            f"Atak: `{user['attack']} (+{atk_bonus})`",
            f"Obrona: `{user['defense']} (+{def_bonus})`",
            "",
            "**❤️ Zdrowie**",
            hp_bar,
            f"`{user['hp']}/{user['max_hp']} HP`",
            "HP odnawia się o `1` punkt co `2 min`.",
            "",
            "**⚡ Stamina**",
            stamina_bar,
            f"`{user['stamina']}/{user['max_stamina']}`",
            "",
            "**💰 Zasoby**",
            f"Złoto: `{user['gold']}`",
            f"Grzybki: `{user['mushrooms']}`",
        ]

        if self.footer:
            rows.extend(["", "━━━━━━━━━━━━━━━━━━━━", self.footer])

        return "\n".join(rows)

    async def build_inventory_tab(self, user):
        items = await get_user_inventory(self.user_id)
        rows = ["### 🎒 EKWIPUNEK", "━━━━━━━━━━━━━━━━━━━━"]

        if not items:
            rows.append("Nie masz jeszcze żadnych przedmiotów.")
            return "\n".join(rows)

        for item in items:
            if item['category'] == 'potion':
                rows.append(f"🧪 **{item['name']}**\nMikstura w torbie. Użyj `/use_potion`.")
            else:
                status = "✅ ZAŁOŻONE" if item['is_equipped'] else "📦 W torbie"
                rows.append(
                    f"⚔️ **{item['name']}**\n"
                    f"{status}\n"
                    f"Atk: `+{item['atk_bonus']}` | Def: `+{item['def_bonus']}`"
                )

        if self.footer:
            rows.append(f"\n━━━━━━━━━━━━━━━━━━━━\n{self.footer}")

        return "\n\n".join(rows)

    async def build_shop_tab(self, user):
        self.shop_items = await get_shop_items_for_user(self.user_id, limit=SHOP_OFFER_SIZE)
        rows = [
            "### 🛒 SKLEP",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💰 Złoto: `{user['gold']}` | 🍄 Grzybki: `{user['mushrooms']}`",
            f"W sklepie jest tylko `{SHOP_OFFER_SIZE}` przedmiotów naraz.",
            "Nie ma stron. Żeby szukać innych rzeczy, odśwież ofertę za `1` grzybka.",
            "Oferta jest dobierana pod Twój poziom oraz kilka pobliskich poziomów.",
            "Przedmioty kupujesz przyciskami pod listą.",
        ]

        if not self.shop_items:
            rows.append("Sklep jest pusty.")
        else:
            for index, item in enumerate(self.shop_items, start=1):
                rows.append(_equipment_line(index, item))

        if self.footer:
            rows.extend(["━━━━━━━━━━━━━━━━━━━━", self.footer])

        return "\n\n".join(rows)

    async def build_potions_tab(self, user):
        self.potion_items = await get_potion_items()
        rows = [
            "### 🧪 SKLEP Z POTKAMI",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💰 Złoto: `{user['gold']}`",
            "Mikstury kupujesz przyciskami pod listą.",
            "Używanie mikstur dalej działa przez `/use_potion` albo `/heal`.",
        ]

        for index, item in enumerate(self.potion_items, start=1):
            rows.append(_potion_line(index, item))

        if self.footer:
            rows.extend(["━━━━━━━━━━━━━━━━━━━━", self.footer])

        return "\n\n".join(rows)

    async def build_tavern_tab(self, user):
        self.quests = await get_random_quests(self.user_id)

        rows = [
            "### 🍻 KARCZMA",
            "Wybierz misję z listy pod panelem karczmy.",
            "Odświeżenie misji kosztuje `1` grzybka i też jest pod panelem.",
            "━━━━━━━━━━━━━━━━━━━━",
            f"❤️ HP: `{user['hp']}/{user['max_hp']}`",
            f"⚡ Stamina: `{user['stamina']}/{user['max_stamina']}`",
            f"💰 Złoto: `{user['gold']}` | 🍄 Grzybki: `{user['mushrooms']}`",
        ]

        if user['on_expedition']:
            rows.append("⚠️ Masz już aktywną misję. Najpierw ją zakończ albo anuluj.")

        if user['stamina'] < 10:
            rows.append("⚡ Masz za mało staminy na misję.")

        if not self.quests:
            rows.append("Nie udało się pobrać misji.")
        else:
            rows.append("\n**📜 Dostępne misje**")
            for index, quest in enumerate(self.quests, 1):
                fight_info = "⚔️ walka" if quest.get('requires_combat', True) else "✅ bez walki, 100% wygranej"
                rows.append(
                    f"**Misja {index}: {quest['name']}**\n"
                    f"{quest.get('difficulty_label', '📜 MISJA')} | {fight_info}\n"
                    f"⏱️ `{quest['duration']} min` | 💰 `{quest['gold']}` | ✨ `{quest['exp']}`"
                )

        if self.footer:
            rows.extend(["━━━━━━━━━━━━━━━━━━━━", self.footer])

        return "\n\n".join(rows)

    async def build_dungeon_tab(self, user):
        monster = get_current_dungeon_monster_from_user(user)
        cooldown = get_dungeon_cooldown_seconds(user)
        cooldown_text = (
            f"⏳ Darmowy atak za `{_format_time(cooldown)}`"
            if cooldown > 0 else
            "✅ Darmowy atak jest dostępny."
        )

        rows = [
            "### 🏰 LOCH",
            "Stałe potwory, stałe poziomy i specjalny przedmiot za ostatniego przeciwnika.",
            "Atakujesz przyciskami pod panelem lochu.",
            "━━━━━━━━━━━━━━━━━━━━",
            f"❤️ HP: `{user['hp']}/{user['max_hp']}`",
            f"⚡ Stamina: `{user['stamina']}/{user['max_stamina']}`",
            f"🍄 Grzybki: `{user['mushrooms']}`",
            cooldown_text,
            "",
            "**Aktualny przeciwnik**",
            f"{monster['name']} `lvl {monster['level']}`",
            f"❤️ HP: `{monster['hp']}` | ⚔️ Atak: `{monster['attack']}` | 🛡️ Obrona: `{monster['defense']}`",
            f"💰 `{monster['gold']}` złota | ✨ `{monster['exp']}` EXP",
        ]

        if user['stamina'] < 10:
            rows.append("⚡ Masz za mało staminy na walkę w lochu.")

        if self.footer:
            rows.extend(["━━━━━━━━━━━━━━━━━━━━", self.footer])

        return "\n".join(rows)

    async def buy_shop_item_from_game(self, interaction: discord.Interaction, item_id: int):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        user = await get_user(self.user_id)
        item = await get_item_by_id(item_id)

        if not user:
            await _send_private(interaction, "❌ Najpierw użyj `/start`.")
            return

        current_offer = await get_shop_items_for_user(self.user_id, limit=SHOP_OFFER_SIZE)
        current_ids = {shop_item['id'] for shop_item in current_offer}
        if item_id not in current_ids:
            self.footer = "⚠️ Ten przedmiot nie jest już w aktualnej ofercie sklepu. Odświeżono panel."
        elif not item or item['category'] != 'equipment':
            self.footer = "❌ Nie ma takiego przedmiotu w sklepie."
        elif 'is_shop_item' in item.keys() and item['is_shop_item'] == 0:
            self.footer = "❌ Tego przedmiotu nie da się kupić. To nagroda specjalna z lochu."
        elif user['level'] < item['level_required']:
            self.footer = f"❌ Ten przedmiot wymaga poziomu `{item['level_required']}`."
        elif user['gold'] < item['price']:
            self.footer = "❌ Nie masz wystarczająco złota."
        else:
            await buy_item(self.user_id, item_id, item['price'])
            self.footer = f"### ✅ Zakup udany\nKupiono: **{item['name']}**."

        await self.reload()
        await interaction.message.edit(view=self)

    async def refresh_shop_from_game(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        ok, message = await refresh_user_shop(self.user_id)
        self.footer = f"### ✅ Oferta odświeżona\n{message}" if ok else f"❌ {message}"
        await self.reload()
        await interaction.message.edit(view=self)

    async def buy_potion_from_game(self, interaction: discord.Interaction, item_id: int):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        user = await get_user(self.user_id)
        item = await get_item_by_id(item_id)

        if not user:
            await _send_private(interaction, "❌ Najpierw użyj `/start`.")
            return

        if not item or item['category'] != 'potion':
            self.footer = "❌ Nie ma takiej mikstury."
        elif user['level'] < item['level_required']:
            self.footer = f"❌ Ta mikstura wymaga poziomu `{item['level_required']}`."
        elif user['gold'] < item['price']:
            self.footer = "❌ Nie masz wystarczająco złota."
        else:
            await buy_item(self.user_id, item_id, item['price'])
            self.footer = f"### ✅ Zakup udany\nKupiono miksturę: **{item['name']}**."

        await self.reload()
        await interaction.message.edit(view=self)

    async def refresh_quests_from_game(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        ok, message = await refresh_user_quests(self.user_id)
        self.footer = f"### ✅ Misje odświeżone\n{message}" if ok else f"❌ {message}"
        await self.reload()
        await interaction.message.edit(view=self)

    async def select_quest_from_game(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        current_user = await get_user(self.user_id)
        if not current_user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", ERROR_COLOR), ephemeral=True)
            return

        if current_user['on_expedition']:
            await interaction.response.send_message(view=message_view("⚠️ Masz już aktywną misję. Najpierw ją zakończ albo anuluj.", WARNING_COLOR), ephemeral=True)
            return

        if current_user['stamina'] < 10:
            await interaction.response.send_message(view=message_view("⚡ Masz za mało staminy na misję.", WARNING_COLOR), ephemeral=True)
            return

        if self.locked:
            await interaction.response.send_message(view=message_view("⚠️ Ta wiadomość ma już wybraną misję. Otwórz karczmę jeszcze raz.", WARNING_COLOR), ephemeral=True)
            return

        self.locked = True
        await interaction.response.defer()

        quest_index = int(interaction.data['values'][0])
        quest = self.quests[quest_index]
        start_time = time.time()
        duration_sec = quest['duration'] * 60

        await update_user(
            self.user_id,
            on_expedition=1,
            expedition_start_time=start_time,
            expedition_duration=quest['duration']
        )

        quest_data = {
            "user_id": self.user_id,
            "monster_name": quest['name'],
            "duration_minutes": quest['duration'],
            "gold_reward": quest['gold'],
            "exp_reward": quest['exp'],
            "difficulty": quest.get('difficulty', 'unknown'),
            "requires_combat": quest.get('requires_combat', True),
            "action": "start_quest",
        }

        try:
            send_to_queue('quest_selections', quest_data)
        except Exception as error:
            print(f"[RABBITMQ ERROR] {error}")

        progress_view = GameQuestProgressView(quest, start_time, duration_sec, self.user_id, self.bot)
        await interaction.message.edit(view=progress_view)
        self.bot.loop.create_task(self.update_quest_progress_from_game(interaction.message, quest, start_time, duration_sec))

    async def update_quest_progress_from_game(self, message, quest, start_time, duration_sec):
        try:
            end_time = start_time + duration_sec
            last_rendered_second = None

            while True:
                current_user = await get_user(self.user_id)
                if not current_user or not current_user['on_expedition']:
                    break

                remaining_float = end_time - time.time()
                remaining_seconds = max(0, math.ceil(remaining_float))

                should_render = (
                    remaining_seconds != last_rendered_second
                    and (remaining_seconds <= 30 or remaining_seconds % 5 == 0)
                )

                if should_render:
                    progress_view = GameQuestProgressView(quest, start_time, duration_sec, self.user_id, self.bot)
                    await message.edit(view=progress_view)
                    last_rendered_second = remaining_seconds

                if remaining_float <= 0:
                    progress_view = GameQuestProgressView(quest, start_time, duration_sec, self.user_id, self.bot)
                    await message.edit(view=progress_view)
                    await asyncio.sleep(2)

                    current_user = await get_user(self.user_id)
                    if not current_user or not current_user['on_expedition']:
                        break

                    if not quest.get('requires_combat', True):
                        await self.finish_easy_quest_from_game(message, quest)
                        break

                    await regenerate_stamina(self.user_id)
                    fresh_user = await get_user(self.user_id)
                    fight_view = FightView(
                        fresh_user,
                        quest['monster'],
                        on_win=self.return_to_game_tavern,
                        on_lose=self.return_to_game_tavern,
                        gold_reward=quest['gold'],
                        exp_reward=quest['exp']
                    )
                    await message.edit(view=fight_view)
                    break

                await asyncio.sleep(1)
        except Exception as error:
            print(f"[GAME QUEST ERROR] {error}")

    async def finish_easy_quest_from_game(self, message, quest):
        current_user = await get_user(self.user_id)
        if not current_user:
            return

        await update_user_after_fight(
            self.user_id,
            current_user['hp'],
            current_user['exp'] + quest['exp'],
            quest['gold'],
            max(0, current_user['stamina'] - 5)
        )
        await update_user(
            self.user_id,
            on_expedition=0,
            expedition_start_time=0,
            expedition_duration=0
        )

        fresh_user = await get_user(self.user_id)

        footer = (
            "### ✅ Misja łatwa zakończona sukcesem\n"
            f"Wykonano zadanie: **{quest['name']}**.\n"
            "Nie było walki z potworem.\n"
            f"💰 Złoto: `+{quest['gold']}`\n"
            f"✨ EXP: `+{quest['exp']}`\n"
            f"{exp_info_line(fresh_user)}\n"
            "⚡ Stamina: `-5`"
        )

        new_view = GameScreenView(self.user_id, self.bot, current_tab="tavern", footer=footer)
        await new_view.reload()
        await message.edit(view=new_view)

    async def return_to_game_tavern(self, interaction: discord.Interaction):
        await update_user(
            self.user_id,
            on_expedition=0,
            expedition_start_time=0,
            expedition_duration=0
        )
        await regenerate_stamina(self.user_id)
        new_view = GameScreenView(self.user_id, self.bot, current_tab="tavern", footer="Wróciłeś do karczmy. Możesz wybrać kolejną misję.")
        await new_view.reload()
        await interaction.followup.edit_message(interaction.message.id, view=new_view)

    async def start_dungeon_from_game(self, interaction: discord.Interaction, use_mushroom: bool):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        await regenerate_stamina(self.user_id)
        user = await get_user(self.user_id)

        if not user:
            await _send_private(interaction, "❌ Najpierw użyj `/start`.")
            return

        if user['stamina'] < 10:
            await _send_private(interaction, "⚡ Masz za mało staminy na walkę w lochu.", WARNING_COLOR)
            return

        ok, message, monster = await start_dungeon_attack(self.user_id, use_mushroom)
        if not ok:
            self.footer = f"⚠️ {message}"
            await self.reload()
            await interaction.message.edit(view=self)
            return

        fresh_user = await get_user(self.user_id)
        fight_view = FightView(
            fresh_user,
            monster,
            on_win=self.on_dungeon_win_from_game,
            on_lose=self.on_dungeon_lose_from_game,
            gold_reward=monster['gold'],
            exp_reward=monster['exp']
        )
        await interaction.message.edit(view=fight_view)

    async def on_dungeon_win_from_game(self, interaction: discord.Interaction):
        result = await complete_dungeon_monster(self.user_id)
        new_view = GameScreenView(self.user_id, self.bot, current_tab="dungeon", footer=result)
        await new_view.reload()
        await interaction.followup.edit_message(interaction.message.id, view=new_view)

    async def on_dungeon_lose_from_game(self, interaction: discord.Interaction):
        footer = (
            "### 💀 Przegrana w lochu\n"
            "Nie przechodzisz dalej. Kolejna próba będzie po 30 minutach albo za grzybka."
        )
        new_view = GameScreenView(self.user_id, self.bot, current_tab="dungeon", footer=footer)
        await new_view.reload()
        await interaction.followup.edit_message(interaction.message.id, view=new_view)

    @staticmethod
    def create_bar(current: int, maximum: int, width: int = 20, fill: str = "█", empty: str = "░") -> str:
        if maximum <= 0:
            return empty * width
        filled = int((current / maximum) * width)
        filled = max(0, min(width, filled))
        return fill * filled + empty * (width - filled)


class GameQuestProgressView(discord.ui.LayoutView):
    def __init__(self, quest, start_time, duration_sec, user_id: str, bot):
        super().__init__(timeout=None)
        self.quest = quest
        self.start_time = start_time
        self.duration_sec = duration_sec
        self.end_time = start_time + duration_sec
        self.user_id = str(user_id)
        self.bot = bot
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = add_container(self, self.get_text(), TAVERN_COLOR)
        cancel_button = ui.Button(label="🛑 Anuluj misję", style=discord.ButtonStyle.danger)
        cancel_button.callback = self.cancel_quest
        add_action_row(container, cancel_button)

    def get_text(self):
        remaining, progress, percent = _quest_progress_values(self.start_time, self.duration_sec)
        is_easy = not self.quest.get('requires_combat', True)
        title = "### 📦 Misja czasowa w toku" if is_easy else "### ⚔️ Misja w toku"
        fight_info = "✅ Bez walki, 100% wygranej" if is_easy else "⚔️ Po czasie rozpocznie się walka"
        bar = "█" * progress + "░" * (10 - progress)

        if remaining == 0:
            time_text = "⏱️ Pozostało: `0 sek`\n⌛ Misja dobiegła końca. Wynik pojawi się za chwilę."
        else:
            time_text = f"⏱️ Pozostało: `{_format_quest_time(remaining)}`"

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

    async def cancel_quest(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/game"):
            return

        await interaction.response.defer()
        current_user = await get_user(self.user_id)
        if not current_user or not current_user['on_expedition']:
            await interaction.followup.send(view=message_view("⚠️ Ta misja jest już zakończona albo anulowana.", WARNING_COLOR), ephemeral=True)
            return

        await update_user_after_fight(
            self.user_id,
            current_user['hp'],
            current_user['exp'],
            0,
            max(0, current_user['stamina'] - 5)
        )
        await update_user(
            self.user_id,
            on_expedition=0,
            expedition_start_time=0,
            expedition_duration=0
        )

        footer = (
            "### ❌ Misja anulowana\n"
            f"Opuściłeś misję: **{self.quest['name']}**.\n"
            "💔 Kara: `-5 staminy`"
        )
        new_view = GameScreenView(self.user_id, self.bot, current_tab="tavern", footer=footer)
        await new_view.reload()
        await interaction.message.edit(view=new_view)
