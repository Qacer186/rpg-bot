import discord
from discord import ui
from database.db import get_user, get_user_inventory, get_all_items, get_equipped_bonuses, get_random_quests, regenerate_stamina


class GameScreenView(discord.ui.View):
    """S&F style game screen with tabs and bottom action buttons."""

    def __init__(self, user_id: str, bot, current_tab: str = "character"):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bot = bot
        self.current_tab = current_tab
        self.setup_buttons()

    def setup_buttons(self):
        self.clear_items()
        self.setup_tabs()
        self.setup_actions()

    def setup_tabs(self):
        char_style = discord.ButtonStyle.primary if self.current_tab == "character" else discord.ButtonStyle.gray
        inv_style = discord.ButtonStyle.primary if self.current_tab == "inventory" else discord.ButtonStyle.gray
        shop_style = discord.ButtonStyle.primary if self.current_tab == "shop" else discord.ButtonStyle.gray

        char_btn = ui.Button(label="👤 POSTAĆ", style=char_style, custom_id="tab_character")
        char_btn.callback = lambda interaction: self.switch_tab(interaction, "character")

        inv_btn = ui.Button(label="🎒 EKWIPUNEK", style=inv_style, custom_id="tab_inventory")
        inv_btn.callback = lambda interaction: self.switch_tab(interaction, "inventory")

        shop_btn = ui.Button(label="🛒 SKLEP", style=shop_style, custom_id="tab_shop")
        shop_btn.callback = lambda interaction: self.switch_tab(interaction, "shop")

        for btn in (char_btn, inv_btn, shop_btn):
            self.add_item(btn)

    def setup_actions(self):
        tavern_btn = ui.Button(label="🍻 KARCZMA", style=discord.ButtonStyle.success, custom_id="action_tavern")
        tavern_btn.callback = lambda interaction: self.switch_tab(interaction, "tavern")

        arena_btn = ui.Button(label="⚔️ ARENA", style=discord.ButtonStyle.danger, custom_id="action_arena")
        arena_btn.callback = lambda interaction: self.switch_tab(interaction, "arena")

        guard_btn = ui.Button(label="🛡️ WARTA", style=discord.ButtonStyle.primary, custom_id="action_guard")
        guard_btn.callback = lambda interaction: self.switch_tab(interaction, "guard")

        blacksmith_btn = ui.Button(label="⚒️ ZBROJOWNIA", style=discord.ButtonStyle.secondary, custom_id="action_blacksmith")
        blacksmith_btn.callback = lambda interaction: self.switch_tab(interaction, "blacksmith")

        for btn in (tavern_btn, arena_btn, guard_btn, blacksmith_btn):
            self.add_item(btn)

    async def switch_tab(self, interaction: discord.Interaction, new_tab: str):
        await interaction.response.defer()
        self.current_tab = new_tab
        self.setup_buttons()
        embed = await self.get_tab_embed()
        await interaction.message.edit(embed=embed, view=self)

    async def get_tab_embed(self):
        user = await get_user(self.user_id)

        if self.current_tab == "character":
            return await self.build_character_tab(user)
        if self.current_tab == "inventory":
            return await self.build_inventory_tab(user)
        if self.current_tab == "shop":
            return await self.build_shop_tab()
        if self.current_tab == "tavern":
            return await self.build_tavern_tab(user)
        if self.current_tab == "arena":
            return await self.build_arena_tab(user)
        if self.current_tab == "guard":
            return await self.build_guard_tab(user)
        if self.current_tab == "blacksmith":
            return await self.build_blacksmith_tab(user)

        return discord.Embed(title="Błąd", description="Nieznany ekran.")

    async def build_character_tab(self, user):
        bonuses = await get_equipped_bonuses(self.user_id)
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        embed = discord.Embed(
            title="⚔️ POSTAĆ",
            description="═══════════════════════════════════════",
            color=0x8b4513
        )
        embed.add_field(
            name="📊 GŁÓWNE",
            value=f"```\nLvl: {user['level']}\nEXP: {user['exp']}\n```",
            inline=True
        )
        embed.add_field(
            name="⚔️ WALKA",
            value=f"```\nAtak: {user['attack']} (+{atk_bonus})\nObrona: {user['defense']} (+{def_bonus})\n```",
            inline=True
        )
        hp_bar = self.create_hp_bar(user['hp'], user['max_hp'], 20)
        stamina_bar = self.create_stamina_bar(user['stamina'], 100, 20)
        embed.add_field(
            name="❤️ ZDROWIE",
            value=f"```\n{hp_bar}\n{user['hp']}/{user['max_hp']} HP\n```",
            inline=False
        )
        embed.add_field(
            name="⚡ STAMINA",
            value=f"```\n{stamina_bar}\n{user['stamina']}/100\n```",
            inline=False
        )
        embed.add_field(
            name="💰 ZASOBY",
            value=f"```\nZłota: {user['gold']}\n```",
            inline=False
        )
        return embed

    async def build_inventory_tab(self, user):
        items = await get_user_inventory(self.user_id)
        embed = discord.Embed(
            title="🎒 EKWIPUNEK",
            description="═══════════════════════════════════════",
            color=0x8b4513
        )
        if not items:
            embed.add_field(name="Pusto!", value="Nie masz jeszcze żadnych przedmiotów.", inline=False)
            return embed
        for item in items:
            status = "✅ ZAŁOŻONE" if item['is_equipped'] else "📦"
            embed.add_field(
                name=f"{item['name']}",
                value=f"{status}\nAtk: +{item['atk_bonus']} | Def: +{item['def_bonus']}",
                inline=False
            )
        return embed

    async def build_shop_tab(self):
        items = await get_all_items()
        embed = discord.Embed(
            title="🛒 SKLEP",
            description="═══════════════════════════════════════",
            color=0x8b4513
        )
        for item in items:
            bonus = f"⚔️ +{item['atk_bonus']}" if item['atk_bonus'] > 0 else f"🛡️ +{item['def_bonus']}"
            embed.add_field(
                name=f"{item['name']} (ID: {item['id']})",
                value=f"Cena: **{item['price']}** złota\n{bonus}",
                inline=False
            )
        return embed

    async def build_tavern_tab(self, user):
        await regenerate_stamina(self.user_id)
        user = await get_user(self.user_id)
        quests = await get_random_quests(self.user_id)

        embed = discord.Embed(
            title="🍻 KARCZMA",
            description="Wybierz misję /tavern, albo użyj przycisku powyżej.",
            color=0x8b4513
        )
        embed.add_field(name="❤️ HP", value=f"{user['hp']}/{user['max_hp']}", inline=True)
        embed.add_field(name="⚡ STAMINA", value=f"{user['stamina']}/100", inline=True)
        embed.add_field(name="💰 ZŁOTO", value=f"{user['gold']}", inline=True)
        embed.add_field(name="═══════════════════════════════════════", value="", inline=False)

        for i, q in enumerate(quests, 1):
            difficulty = "🟢 ŁATWA" if q['gold'] < 100 else "🟡 ŚREDNIA" if q['gold'] < 300 else "🔴 TRUDNA"
            embed.add_field(
                name=f"Misja {i}: {q['name']}",
                value=f"{difficulty}\n⏱️ {q['duration']} min | 💰 {q['gold']} | ✨ {q['exp']}",
                inline=False
            )
        return embed

    async def build_arena_tab(self, user):
        embed = discord.Embed(
            title="⚔️ ARENA",
            description="Przygotuj się do pojedynku. Tutaj w przyszłości będą funkcje walki turniejowej.",
            color=0xe74c3c
        )
        embed.add_field(name="❤️ HP", value=f"{user['hp']}/{user['max_hp']}", inline=True)
        embed.add_field(name="⚡ STAMINA", value=f"{user['stamina']}/100", inline=True)
        return embed

    async def build_guard_tab(self, user):
        embed = discord.Embed(
            title="🛡️ WARTA",
            description="Zabezpiecz miasto i zarabiaj nagrody. Funkcja w przygotowaniu.",
            color=0x3498db
        )
        return embed

    async def build_blacksmith_tab(self, user):
        embed = discord.Embed(
            title="⚒️ ZBROJOWNIA",
            description="Naprawiaj ekwipunek i kupuj nowe przedmioty. Użyj /shop, /buy lub /inventory.",
            color=0x95a5a6
        )
        return embed

    @staticmethod
    def create_hp_bar(current: int, maximum: int, width: int = 20) -> str:
        filled = int((current / maximum) * width)
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def create_stamina_bar(current: int, maximum: int, width: int = 20) -> str:
        filled = int((current / maximum) * width)
        return "▓" * filled + "░" * (width - filled)
