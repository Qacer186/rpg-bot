import discord
from discord import ui

from database.db import (
    buy_item,
    get_item_by_id,
    get_potion_items,
    get_shop_items_for_user,
    get_user,
    refresh_user_shop,
)
from utils.containers import add_action_row, add_container, message_view
from utils.security import ensure_view_owner


SHOP_COLOR = 0xF1C40F
POTION_COLOR = 0x9B59B6
ERROR_COLOR = 0xE74C3C
SUCCESS_COLOR = 0x2ECC71
SHOP_OFFER_SIZE = 5


def _equipment_line(index: int, item):
    parts = []
    if item['atk_bonus']:
        parts.append(f"⚔️ +{item['atk_bonus']}")
    if item['def_bonus']:
        parts.append(f"🛡️ +{item['def_bonus']}")
    bonus = " | ".join(parts) if parts else "brak bonusu"
    return (
        f"**{index}. {item['name']}** | ID: `{item['id']}`\n"
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
        f"**{index}. {item['name']}** | ID: `{item['id']}`\n"
        f"Cena: `{item['price']}` złota | Lvl: `{item['level_required']}` | {effect}"
    )


def _chunk(items, size=5):
    for index in range(0, len(items), size):
        yield items[index:index + size]


async def _send_private(interaction: discord.Interaction, text: str, color: int = ERROR_COLOR):
    view = message_view(text, color)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


class EquipmentShopView(discord.ui.LayoutView):
    def __init__(self, user_id: str, footer: str | None = None):
        super().__init__(timeout=None)
        self.user_id = str(user_id)
        self.footer = footer
        self.items = []
        self.user = None

    async def reload(self):
        self.clear_items()
        self.user = await get_user(self.user_id)
        self.items = await get_shop_items_for_user(self.user_id, limit=SHOP_OFFER_SIZE) if self.user else []
        container = add_container(self, self._build_text(), SHOP_COLOR)
        self._setup_buttons(container)

    def _build_text(self):
        if not self.user:
            return "❌ Najpierw użyj `/start`."

        rows = [
            "### 🛒 Sklep z ekwipunkiem",
            f"💰 Złoto: `{self.user['gold']}` | 🍄 Grzybki: `{self.user['mushrooms']}`",
            f"W sklepie jest tylko `{SHOP_OFFER_SIZE}` przedmiotów naraz.",
            "Nie ma stron. Żeby szukać innych rzeczy, odśwież ofertę za `1` grzybka.",
            "Oferta jest dobierana pod Twój poziom oraz kilka pobliskich poziomów.",
            "Przedmioty kupujesz przyciskami w tym samym panelu.",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if not self.items:
            rows.append("Sklep jest pusty.")
        else:
            for index, item in enumerate(self.items, start=1):
                rows.append(_equipment_line(index, item))

        if self.footer:
            rows.append("━━━━━━━━━━━━━━━━━━━━")
            rows.append(self.footer)

        return "\n\n".join(rows)

    def _setup_buttons(self, container):
        if not self.user:
            return

        buy_buttons = []
        for index, item in enumerate(self.items, start=1):
            button = ui.Button(
                label=f"Kup {index}",
                style=discord.ButtonStyle.primary,
                disabled=self.user['gold'] < item['price'] or self.user['level'] < item['level_required'],
            )
            button.callback = lambda interaction, item_id=item['id']: self.buy_from_button(interaction, item_id)
            buy_buttons.append(button)

        if buy_buttons:
            add_action_row(container, *buy_buttons)

        refresh_button = ui.Button(
            label="🍄 Odśwież sklep",
            style=discord.ButtonStyle.success,
            disabled=self.user['mushrooms'] < 1,
        )
        refresh_button.callback = self.refresh_from_button
        add_action_row(container, refresh_button, separator=not bool(buy_buttons))

    async def buy_from_button(self, interaction: discord.Interaction, item_id: int):
        if not await ensure_view_owner(interaction, self.user_id, "/shop"):
            return

        await interaction.response.defer()
        user = await get_user(self.user_id)
        if not user:
            await _send_private(interaction, "❌ Najpierw użyj `/start`.")
            return

        current_offer = await get_shop_items_for_user(self.user_id, limit=SHOP_OFFER_SIZE)
        current_ids = {item['id'] for item in current_offer}
        if item_id not in current_ids:
            self.footer = "⚠️ Ten przedmiot nie jest już w aktualnej ofercie sklepu. Odświeżono widok."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        item = await get_item_by_id(item_id)
        if not item or item['category'] != 'equipment':
            self.footer = "❌ Nie ma takiego przedmiotu w sklepie."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        if 'is_shop_item' in item.keys() and item['is_shop_item'] == 0:
            self.footer = "❌ Tego przedmiotu nie da się kupić. To nagroda specjalna z lochu."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        if user['level'] < item['level_required']:
            self.footer = f"❌ Ten przedmiot wymaga poziomu `{item['level_required']}`."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        if user['gold'] < item['price']:
            self.footer = "❌ Nie masz wystarczająco złota."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        await buy_item(self.user_id, item_id, item['price'])
        self.footer = f"### ✅ Zakup udany\nKupiono: **{item['name']}**."
        await self.reload()
        await interaction.message.edit(view=self)

    async def refresh_from_button(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user_id, "/shop"):
            return

        await interaction.response.defer()
        ok, message = await refresh_user_shop(self.user_id)
        if ok:
            self.footer = f"### ✅ Oferta odświeżona\n{message}"
        else:
            self.footer = f"❌ {message}"

        await self.reload()
        await interaction.message.edit(view=self)


class PotionShopView(discord.ui.LayoutView):
    def __init__(self, user_id: str, footer: str | None = None):
        super().__init__(timeout=None)
        self.user_id = str(user_id)
        self.footer = footer
        self.items = []
        self.user = None

    async def reload(self):
        self.clear_items()
        self.user = await get_user(self.user_id)
        self.items = await get_potion_items() if self.user else []
        container = add_container(self, self._build_text(), POTION_COLOR)
        self._setup_buttons(container)

    def _build_text(self):
        if not self.user:
            return "❌ Najpierw użyj `/start`."

        rows = [
            "### 🧪 Sklep z miksturami",
            f"💰 Złoto: `{self.user['gold']}`",
            "Mikstury kupujesz przyciskami w tym samym panelu.",
            "Używanie mikstur dalej działa komendą `/use_potion` albo `/heal`.",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        for index, item in enumerate(self.items, start=1):
            rows.append(_potion_line(index, item))

        if self.footer:
            rows.append("━━━━━━━━━━━━━━━━━━━━")
            rows.append(self.footer)

        return "\n\n".join(rows)

    def _setup_buttons(self, container):
        if not self.user:
            return

        buy_buttons = []
        for index, item in enumerate(self.items, start=1):
            button = ui.Button(
                label=f"Kup {index}",
                style=discord.ButtonStyle.primary,
                disabled=self.user['gold'] < item['price'] or self.user['level'] < item['level_required'],
            )
            button.callback = lambda interaction, item_id=item['id']: self.buy_potion_from_button(interaction, item_id)
            buy_buttons.append(button)

        for row_buttons in _chunk(buy_buttons, 5):
            add_action_row(container, *row_buttons)

    async def buy_potion_from_button(self, interaction: discord.Interaction, item_id: int):
        if not await ensure_view_owner(interaction, self.user_id, "/potion_shop"):
            return

        await interaction.response.defer()
        user = await get_user(self.user_id)
        if not user:
            await _send_private(interaction, "❌ Najpierw użyj `/start`.")
            return

        item = await get_item_by_id(item_id)
        if not item or item['category'] != 'potion':
            self.footer = "❌ Nie ma takiej mikstury."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        if user['level'] < item['level_required']:
            self.footer = f"❌ Ta mikstura wymaga poziomu `{item['level_required']}`."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        if user['gold'] < item['price']:
            self.footer = "❌ Nie masz wystarczająco złota."
            await self.reload()
            await interaction.message.edit(view=self)
            return

        await buy_item(self.user_id, item_id, item['price'])
        self.footer = f"### ✅ Zakup udany\nKupiono miksturę: **{item['name']}**."
        await self.reload()
        await interaction.message.edit(view=self)
