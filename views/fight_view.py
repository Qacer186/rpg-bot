import discord
import random
from discord import ui
from database.db import update_user_after_fight, get_equipped_bonuses, get_user


class FightView(discord.ui.View):
    def __init__(self, user_data, monster, on_win=None, on_lose=None):
        super().__init__(timeout=None)  # Manual timeout - fights can be long
        self.user = user_data
        self.monster = monster
        self.on_win = on_win
        self.on_lose = on_lose
        # Local HP copy for fight simulation (DB updated only on end_fight)
        self.user_hp = user_data['hp']
        self.monster_hp = monster['hp']
        self.setup_fight_buttons()
    
    def setup_fight_buttons(self):
        """Create fight UI with ActionRow"""
        self.clear_items()
        
        row = ui.ActionRow()
        attack_btn = ui.Button(label="⚔️ Atakuj", style=discord.ButtonStyle.danger)
        attack_btn.callback = self.attack
        row.add_item(attack_btn)
        
        for item in row.children:
            self.add_item(item)

    async def attack(self, interaction: discord.Interaction):
        """Execute attack action in fight"""
        await interaction.response.defer()
        
        # Fetch equipment bonuses from database
        bonuses = await get_equipped_bonuses(self.user['discord_id'])

        # Handle NULL from aggregate query when no equipped items
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        # Player attack: base stat + equipment bonus +/- variance
        dmg = random.randint(
            self.user['attack'] + atk_bonus - 2, 
            self.user['attack'] + atk_bonus + 5
        )
        self.monster_hp -= dmg
        log_msg = f"Zadałeś **{dmg}** obrażeń potworowi {self.monster['name']}!"

        # Check if monster HP <= 0
        if self.monster_hp <= 0:
            await self.end_fight(interaction, True)
            return

        # Monster counter-attack: monster_attack - (player_defense + equipment_bonus)
        # Clamp to 0 minimum (no healing from defense)
        m_dmg = max(0, self.monster['attack'] - (self.user['defense'] + def_bonus))
        self.user_hp -= m_dmg
        log_msg += f"\nPotwór oddaje za **{m_dmg}**!"

        # Check if player HP <= 0
        if self.user_hp <= 0:
            await self.end_fight(interaction, False)
            return

        # Update fight UI
        await self.update_message(interaction, log_msg)

    async def update_message(self, interaction, log_msg):
        """Update fight display with current HP and combat log"""
        embed = discord.Embed(title=f"⚔️ Walka z {self.monster['name']}", color=0xe74c3c)
        
        # Player HP bar
        player_hp_percent = int((self.user_hp / self.user['max_hp']) * 10)
        player_bar = "❤️" * player_hp_percent + "🖤" * (10 - player_hp_percent)
        
        # Monster HP bar
        monster_hp_percent = int((self.monster_hp / self.monster['hp']) * 10)
        monster_bar = "❤️" * monster_hp_percent + "🖤" * (10 - monster_hp_percent)
        
        embed.add_field(name="👤 Ty", value=f"HP: {self.user_hp}/{self.user['max_hp']}\n{player_bar}", inline=False)
        embed.add_field(name=f"👹 {self.monster['name']}", value=f"HP: {self.monster_hp}/{self.monster['hp']}\n{monster_bar}", inline=False)
        embed.set_footer(text=log_msg)
        
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)

    async def end_fight(self, interaction, win):
        """Handle fight end: update database, show result, transition to tavern"""
        # Fetch current user state from DB to ensure no stale exp values
        current_user = await get_user(self.user['discord_id'])
        
        if win:
            # Victory: grant 20 EXP + gold reward, reduce stamina by 10
            gold = self.monster['gold']
            exp = 20
            await update_user_after_fight(self.user['discord_id'], self.user_hp, current_user['exp'] + exp, gold, current_user['stamina'] - 10)
            
            embed = discord.Embed(
                title="🏆 WYGRANA!",
                description=f"Pokonałeś {self.monster['name']}!",
                color=0x2ecc71
            )
            embed.add_field(name="💰 Złoto", value=f"+{gold}", inline=True)
            embed.add_field(name="✨ Doświadczenie", value=f"+{exp} EXP", inline=True)
            embed.add_field(name="❤️ Twoje HP", value=f"{self.user_hp}/{self.user['max_hp']}", inline=True)
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
            
            if self.on_win:
                await self.on_win(interaction)
                return
        else:
            # Loss: no EXP gain, use current DB value unchanged to prevent stale exp inflation
            # Reset HP to 20, reduce stamina by 10
            await update_user_after_fight(self.user['discord_id'], 20, current_user['exp'], 0, current_user['stamina'] - 10)
            
            embed = discord.Embed(
                title="💀 PRZEGRANA",
                description=f"{self.monster['name']} Cię pokonał...",
                color=0xe74c3c
            )
            embed.add_field(name="❤️ Pozostało HP", value="20", inline=True)
            embed.add_field(name="💰 Strata", value="0 złota", inline=True)
            embed.add_field(name="✨ Strata", value="0 EXP", inline=True)
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
            
            if self.on_lose:
                await self.on_lose(interaction)
                return

        # Fallback if no callback defined
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)