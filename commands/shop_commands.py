import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_all_items, get_item_by_id, get_user_inventory, buy_item, toggle_equip_item, use_item, get_user, update_user


class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Otwiera sklep")
    async def shop(self, interaction: discord.Interaction):
        items = await get_all_items()
        embed = discord.Embed(title="🛒 Sklep", color=0xf1c40f)
        for item in items:
            bonus = f"⚔️ +{item['atk_bonus']}" if item['atk_bonus'] > 0 else f"🛡️ +{item['def_bonus']}"
            embed.add_field(name=f"{item['name']} (ID: {item['id']})", value=f"Cena: {item['price']} | {bonus}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Kupuje przedmiot")
    async def buy(self, interaction: discord.Interaction, item_id: int):
        user = await get_user(str(interaction.user.id))
        item = await get_item_by_id(item_id)

        if not item:
            await interaction.response.send_message("❌ Nie ma takiego przedmiotu!", ephemeral=True)
            return

        if user['gold'] < item['price']:
            await interaction.response.send_message("❌ Nie masz wystarczająco złota!", ephemeral=True)
            return

        await buy_item(str(interaction.user.id), item_id, item['price'])
        await interaction.response.send_message(f"✅ Kupiono: {item['name']}!")

    @app_commands.command(name="inventory", description="Twój ekwipunek")
    async def inventory(self, interaction: discord.Interaction):
        items = await get_user_inventory(str(interaction.user.id))
        if not items:
            await interaction.response.send_message("Pusto!", ephemeral=True)
            return

        embed = discord.Embed(title="🎒 Ekwipunek", color=0x95a5a6)
        for item in items:
            status = "✅ Założone" if item['is_equipped'] else "📦 W torbie"
            embed.add_field(name=item['name'], value=status, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="equip", description="Zakłada lub zdejmuje przedmiot")
    async def equip(self, interaction: discord.Interaction, item_name: str):
        user_id = str(interaction.user.id)
        item_name_found, status = await toggle_equip_item(user_id, item_name)

        if not item_name_found:
            await interaction.response.send_message("Nie masz tego przedmiotu!", ephemeral=True)
            return

        action = "Założono" if status else "Zdjęto"
        await interaction.response.send_message(f"✅ **{action}:** {item_name_found}")

    @app_commands.command(name="heal", description="Używa mikstury HP")
    async def heal(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if await use_item(user_id, 'Mikstura HP'):
            await update_user(user_id, hp=user['max_hp'])
            await interaction.response.send_message("❤️ HP odnowione!")
        else:
            await interaction.response.send_message("❌ Nie masz mikstur!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
