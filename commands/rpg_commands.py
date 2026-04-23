import discord
from discord import app_commands, ui
from discord.ext import commands
import random
import time
import asyncio

from database.db import get_user, create_user, get_leaderboard, buy_item, get_user_inventory, update_user, use_item, get_all_items, get_item_by_id, toggle_equip_item, get_random_quests, regenerate_stamina
from views.fight_view import FightView
from services.monster_service import get_random_monster
from services.rabbitmq import send_to_queue


class QuestProgressView(discord.ui.View):
    def __init__(self, quest, start_time, duration_sec, user_data, bot):
        super().__init__(timeout=None)  # Manual timeout management, handles quest duration
        self.quest = quest
        self.start_time = start_time
        self.duration_sec = duration_sec
        self.end_time = start_time + duration_sec
        self.user_data = user_data
        self.bot = bot
        self.setup_buttons()

    def setup_buttons(self):
        """Create button layout with ActionRows"""
        self.clear_items()
        
        # Row 1: Quest name
        row1 = ui.ActionRow()
        row1.add_item(ui.Button(label=f"⚔️ {self.quest['name']}", style=discord.ButtonStyle.blurple, disabled=True))
        self.add_item(row1.children[0])
        
        # Row 2: Progress bar
        elapsed = time.time() - self.start_time
        remaining = self.duration_sec - elapsed
        
        if remaining > 0:
            progress = int((elapsed / self.duration_sec) * 10)
            bar = "█" * progress + "░" * (10 - progress)
            percent = int((elapsed / self.duration_sec) * 100)
            row2 = ui.ActionRow()
            row2.add_item(ui.Button(label=f"📊 [{bar}] {percent}%", style=discord.ButtonStyle.gray, disabled=True))
            self.add_item(row2.children[0])
        else:
            row2 = ui.ActionRow()
            row2.add_item(ui.Button(label="✅ Gotowe!", style=discord.ButtonStyle.success, disabled=True))
            self.add_item(row2.children[0])
        
        # Row 3: Rewards
        row3 = ui.ActionRow()
        row3.add_item(ui.Button(label=f"💰 {self.quest['gold']} złota", style=discord.ButtonStyle.success, disabled=True))
        row3.add_item(ui.Button(label=f"✨ {self.quest['exp']} EXP", style=discord.ButtonStyle.primary, disabled=True))
        for item in row3.children:
            self.add_item(item)

    def get_timestamp_embed(self):
        """Create embed with native Discord dynamic timestamp (auto-updates on client)"""
        embed = discord.Embed(title="⚔️ Misja w toku", color=0x6b4226)
        
        # Use Discord's native timestamp format <t:unix:R> for automatic countdown display
        end_unix = int(self.end_time)
        timestamp = f"<t:{end_unix}:R>"
        
        embed.add_field(name="📍 Cel", value=self.quest['name'], inline=False)
        embed.add_field(name="⏱️ Koniec", value=timestamp, inline=False)
        embed.add_field(name="💰 Nagroda", value=f"{self.quest['gold']} złota + {self.quest['exp']} EXP", inline=False)
        
        return embed

class QuestView(discord.ui.View):
    def __init__(self, user_data, quests, bot):
        super().__init__(timeout=None)
        self.user_data = user_data
        self.quests = quests
        self.bot = bot
        self.setup_quest_select()

    def setup_quest_select(self):
        """Create quest selection as SELECT MENU instead of buttons"""
        self.clear_items()
        
        # Create select menu with quest options
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
        """Handle quest selection from dropdown menu"""
        await interaction.response.defer()
        
        quest_idx = int(interaction.data['values'][0])
        quest = self.quests[quest_idx]
        
        # Publish quest to RabbitMQ
        quest_data = {
            "user_id": self.user_data['discord_id'],
            "monster_name": quest['name'],
            "duration_minutes": quest['duration'],
            "gold_reward": quest['gold'],
            "exp_reward": quest['exp'],
            "action": "start_quest"
        }
        send_to_queue('quest_selections', quest_data)
        
        # Disable select menu
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        # Initialize quest progress view
        start_time = time.time()
        duration_sec = quest['duration'] * 60
        progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
        
        # Initial progress message with nice embed
        progress_embed = progress_view.get_timestamp_embed()
        await interaction.followup.edit_message(
            interaction.message.id,
            embed=progress_embed,
            view=progress_view
        )
        
        # Schedule timer task
        self.bot.loop.create_task(self.update_quest_progress(interaction.message, quest, start_time, duration_sec))

    async def update_quest_progress(self, followup, quest, start_time, duration_sec):
        try:
            while True:
                elapsed = time.time() - start_time
                remaining = duration_sec - elapsed
                
                if remaining <= 0:
                    fight_view = FightView(self.user_data, quest['monster'], on_win=self.return_to_tavern, on_lose=self.return_to_tavern)
                    embed = discord.Embed(
                        title="⚔️ Natrafiłeś na potwora!",
                        description=f"Przed tobą stanął **{quest['monster']['name']}**!",
                        color=0xe74c3c
                    )
                    await followup.edit(embed=embed, view=fight_view)
                    break
                
                # Update every ~10 sec or more often when time is short
                if elapsed % 10 < 2 or remaining < 30:
                    progress_view = QuestProgressView(quest, start_time, duration_sec, self.user_data, self.bot)
                    progress_embed = progress_view.get_timestamp_embed()
                    await followup.edit(embed=progress_embed, view=progress_view)
                
                await asyncio.sleep(2)
        except Exception as e:
            print(f"[QUEST ERROR] {e}")
            try:
                fight_view = FightView(self.user_data, quest['monster'], on_win=self.return_to_tavern, on_lose=self.return_to_tavern)
                embed = discord.Embed(
                    title="⚔️ Natrafiłeś na potwora!",
                    description=f"Przed tobą stanął **{quest['monster']['name']}**!",
                    color=0xe74c3c
                )
                await followup.edit(embed=embed, view=fight_view)
            except:
                pass

    async def return_to_tavern(self, interaction):
        try:
            await regenerate_stamina(self.user_data['discord_id'])
            quests = await get_random_quests(self.user_data['discord_id'])
            quest_view = QuestView(self.user_data, quests, self.bot)
            
            embed = discord.Embed(
                title="🍻 Karczma u Podpitego Goblina",
                description="Wybierz nową misję",
                color=0x6b4226
            )
            for i, q in enumerate(quests, 1):
                difficulty = "🟢 Łatwa" if q['gold'] < 100 else "🟡 Średnia" if q['gold'] < 300 else "🔴 Trudna"
                embed.add_field(
                    name=f"Misja {i}: {q['name']}",
                    value=f"{difficulty} | ⏱️ {q['duration']}m | 💰 {q['gold']} | ✨ {q['exp']}",
                    inline=False
                )
            
            await interaction.response.edit_message(embed=embed, view=quest_view)
        except Exception as e:
            print(f"[TAVERN ERROR] {e}")

    @discord.ui.button(label="Misja 1", style=discord.ButtonStyle.primary)
    async def quest_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_quest(interaction, 0)

    @discord.ui.button(label="Misja 2", style=discord.ButtonStyle.success)
    async def quest_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_quest(interaction, 1)

    @discord.ui.button(label="Misja 3", style=discord.ButtonStyle.danger)
    async def quest_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_quest(interaction, 2)



class RPGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def create_progress_bar(current, maximum, length=10):
        filled = int(length * current / maximum)
        return "🟩" * filled + "⬜" * (length - filled)

    @app_commands.command(name="start", description="Tworzy postać")
    async def start(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if user:
            await interaction.response.send_message("❌ Już masz postać!", ephemeral=True)
        else:
            await create_user(user_id)
            embed = discord.Embed(title="🧙 Postać utworzona!", description="Powodzenia, bohaterze!", color=0x00ff00)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="profile", description="Pokazuje profil gracza")
    async def profile(self, interaction: discord.Interaction):
        user = await get_user(str(interaction.user.id))
        if not user:
            await interaction.response.send_message("Użyj /start!", ephemeral=True)
            return

        embed = discord.Embed(title=f"👤 Profil {interaction.user.name}", color=0x3498db)
        stamina_bar = self.create_progress_bar(user['stamina'], 100)
        
        embed.add_field(name="🎯 Statystyki", value=f"**Lvl:** {user['level']} | **EXP:** {user['exp']}", inline=True)
        embed.add_field(name="⚔️ Bojowe", value=f"**Atak:** {user['attack']} | **Obrona:** {user['defense']}", inline=True)
        embed.add_field(name="⚡ Stamina", value=f"{stamina_bar} ({user['stamina']}/100)", inline=False)
        embed.add_field(name="💰 Portfel", value=f"{user['gold']} złota", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tavern", description="Odwiedź karczmę i wybierz misję")
    async def tavern(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        
        if not user:
            await interaction.followup.send("Najpierw użyj /start!", ephemeral=True)
            return

        await regenerate_stamina(user_id)
        user = await get_user(user_id)

        if user['stamina'] < 10:
            await interaction.followup.send("⚡ Za mało staminy! Odpocznij chwilę.", ephemeral=True)
            return

        quests = await get_random_quests(user_id)
        
        embed = discord.Embed(
            title="🍻 Karczma u Podpitego Goblina",
            description="Wybierz misję do wykonania",
            color=0x6b4226
        )
        
        for i, q in enumerate(quests, 1):
            difficulty = "🟢 Łatwa" if q['gold'] < 100 else "🟡 Średnia" if q['gold'] < 300 else "🔴 Trudna"
            embed.add_field(
                name=f"Misja {i}: {q['name']}",
                value=f"{difficulty}\n⏱️ {q['duration']} min | 💰 {q['gold']} | ✨ {q['exp']}",
                inline=False
            )
        
        embed.set_footer(text=f"⚡ Stamina: {user['stamina']}/100")
        
        view = QuestView(user, quests, self.bot)
        await interaction.followup.send(embed=embed, view=view)

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

    @app_commands.command(name="expedition_status", description="Sprawdź status swojej misji")
    async def expedition_status(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user = await get_user(user_id)
        if not user:
            await interaction.response.send_message("Najpierw użyj /start!", ephemeral=True)
            return

        if user['on_expedition']:
            elapsed = time.time() - user['expedition_start_time']
            remaining = user['expedition_duration'] * 60 - elapsed
            if remaining > 0:
                min_left = int(remaining // 60)
                sec_left = int(remaining % 60)
                await interaction.response.send_message(f"⚔️ Jesteś na misji! Pozostało: {min_left} min {sec_left} sek")
            else:
                await interaction.response.send_message("Misja powinna już się zakończyć! Spróbuj ponownie za chwilę.")
        else:
            await interaction.response.send_message("Nie jesteś obecnie na misji.")

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
    await bot.add_cog(RPGCog(bot))