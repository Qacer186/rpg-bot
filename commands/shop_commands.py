import discord
from discord import app_commands
from discord.ext import commands

from database.db import (
    buy_item,
    get_item_by_id,
    get_potion_items,
    get_shop_items_for_user,
    get_user,
    get_user_inventory,
    refresh_user_shop,
    toggle_equip_item,
    update_user,
    use_potion,
)
from utils.containers import message_view
from views.shop_view import EquipmentShopView, PotionShopView


def _equipment_line(item):
    parts = []
    if item['atk_bonus']:
        parts.append(f"⚔️ +{item['atk_bonus']}")
    if item['def_bonus']:
        parts.append(f"🛡️ +{item['def_bonus']}")
    bonus = " | ".join(parts) if parts else "brak bonusu"
    return (
        f"**{item['name']}** | ID: `{item['id']}`\n"
        f"Cena: `{item['price']}` złota | Lvl: `{item['level_required']}` | {bonus}"
    )


def _potion_line(item):
    effect = {
        "heal": f"leczy `{item['effect_value']}` HP",
        "full_heal": "leczy do pełna",
        "stamina": f"odnawia `{item['effect_value']}` staminy",
        "attack": f"dodaje `+{item['effect_value']}` ataku",
        "defense": f"dodaje `+{item['effect_value']}` obrony",
        "max_hp": f"dodaje `+{item['effect_value']}` max HP",
    }.get(item['effect_type'], "specjalne działanie")

    return (
        f"**{item['name']}** | ID: `{item['id']}`\n"
        f"Cena: `{item['price']}` złota | Lvl: `{item['level_required']}` | {effect}"
    )


class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Otwiera sklep z ekwipunkiem")
    async def shop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        view = EquipmentShopView(user_id)
        await view.reload()
        await interaction.response.send_message(view=view)

    @app_commands.command(name="refresh_shop", description="Odświeża sklep za 1 grzybka")
    async def refresh_shop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        ok, message = await refresh_user_shop(user_id)
        footer = f"### ✅ Oferta odświeżona\n{message}" if ok else f"❌ {message}"
        view = EquipmentShopView(user_id, footer=footer)
        await view.reload()
        await interaction.response.send_message(view=view, ephemeral=not ok)

    @app_commands.command(name="buy", description="Kupuje przedmiot ze sklepu")
    async def buy(self, interaction: discord.Interaction, item_id: int):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        item = await get_item_by_id(item_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if not item:
            await interaction.response.send_message(view=message_view("❌ Nie ma takiego przedmiotu!", 0xE74C3C), ephemeral=True)
            return

        if item['category'] != 'equipment':
            await interaction.response.send_message(view=message_view("❌ To nie jest przedmiot z normalnego sklepu. Do mikstur użyj `/buy_potion`.", 0xE74C3C), ephemeral=True)
            return

        current_offer = await get_shop_items_for_user(user_id, limit=5)
        current_ids = {shop_item['id'] for shop_item in current_offer}
        if item_id not in current_ids:
            await interaction.response.send_message(
                view=message_view("❌ Ten przedmiot nie jest w aktualnej ofercie. Użyj `/shop` albo odśwież sklep za grzybka.", 0xE74C3C),
                ephemeral=True
            )
            return

        if 'is_shop_item' in item.keys() and item['is_shop_item'] == 0:
            await interaction.response.send_message(view=message_view("❌ Tego przedmiotu nie da się kupić. To nagroda specjalna z lochu.", 0xE74C3C), ephemeral=True)
            return

        if user['level'] < item['level_required']:
            await interaction.response.send_message(view=message_view(f"❌ Ten przedmiot wymaga poziomu `{item['level_required']}`.", 0xE74C3C), ephemeral=True)
            return

        if user['gold'] < item['price']:
            await interaction.response.send_message(view=message_view("❌ Nie masz wystarczająco złota!", 0xE74C3C), ephemeral=True)
            return

        await buy_item(user_id, item_id, item['price'])
        await interaction.response.send_message(view=message_view(f"### ✅ Zakup udany\nKupiono: **{item['name']}**", 0x2ECC71))

    @app_commands.command(name="potion_shop", description="Otwiera osobny sklep z miksturami")
    async def potion_shop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        view = PotionShopView(user_id)
        await view.reload()
        await interaction.response.send_message(view=view)

    @app_commands.command(name="buy_potion", description="Kupuje miksturę")
    async def buy_potion(self, interaction: discord.Interaction, item_id: int):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        item = await get_item_by_id(item_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        if not item or item['category'] != 'potion':
            await interaction.response.send_message(view=message_view("❌ Nie ma takiej mikstury.", 0xE74C3C), ephemeral=True)
            return

        if user['level'] < item['level_required']:
            await interaction.response.send_message(view=message_view(f"❌ Ta mikstura wymaga poziomu `{item['level_required']}`.", 0xE74C3C), ephemeral=True)
            return

        if user['gold'] < item['price']:
            await interaction.response.send_message(view=message_view("❌ Nie masz wystarczająco złota!", 0xE74C3C), ephemeral=True)
            return

        await buy_item(user_id, item_id, item['price'])
        await interaction.response.send_message(view=message_view(f"### ✅ Zakup udany\nKupiono miksturę: **{item['name']}**", 0x2ECC71))

    @app_commands.command(name="inventory", description="Twój ekwipunek")
    async def inventory(self, interaction: discord.Interaction):
        items = await get_user_inventory(str(interaction.user.id))
        if not items:
            await interaction.response.send_message(view=message_view("### 🎒 Ekwipunek\nPusto!", 0x95A5A6), ephemeral=True)
            return

        rows = ["### 🎒 Ekwipunek", "━━━━━━━━━━━━━━━━━━━━"]
        for item in items:
            if item['category'] == 'potion':
                rows.append(f"🧪 **{item['name']}** | mikstura")
            else:
                status = "✅ Założone" if item['is_equipped'] else "📦 W torbie"
                rows.append(
                    f"⚔️ **{item['name']}** | {status}\n"
                    f"Atk: `+{item['atk_bonus']}` | Def: `+{item['def_bonus']}`"
                )

        await interaction.response.send_message(view=message_view("\n\n".join(rows), 0x95A5A6))

    @app_commands.command(name="equip", description="Zakłada lub zdejmuje przedmiot")
    async def equip(self, interaction: discord.Interaction, item_name: str):
        user_id = str(interaction.user.id)
        item_name_found, status = await toggle_equip_item(user_id, item_name)

        if not item_name_found:
            await interaction.response.send_message(view=message_view("❌ Nie masz takiego przedmiotu do założenia!", 0xE74C3C), ephemeral=True)
            return

        action = "Założono" if status else "Zdjęto"
        await interaction.response.send_message(view=message_view(f"### ✅ Ekwipunek zmieniony\n**{action}:** {item_name_found}", 0x2ECC71))

    @app_commands.command(name="use_potion", description="Używa mikstury z ekwipunku")
    async def use_potion_command(self, interaction: discord.Interaction, potion_name: str):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        ok, message = await use_potion(user_id, potion_name)
        if ok:
            await interaction.response.send_message(view=message_view(f"### 🧪 Mikstura użyta\n{message}", 0x9B59B6))
        else:
            await interaction.response.send_message(view=message_view(f"❌ {message}", 0xE74C3C), ephemeral=True)

    @app_commands.command(name="heal", description="Używa mikstury HP")
    async def heal(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)

        if not user:
            await interaction.response.send_message(view=message_view("❌ Najpierw użyj `/start`!", 0xE74C3C), ephemeral=True)
            return

        ok, message = await use_potion(user_id, "Mikstura HP")
        if ok:
            await interaction.response.send_message(view=message_view(f"### ❤️ Leczenie\n{message}", 0x2ECC71))
        else:
            await interaction.response.send_message(view=message_view(f"❌ {message}", 0xE74C3C), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
