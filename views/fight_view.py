import discord
import random
from database.db import update_user_after_fight, get_equipped_bonuses, get_user

class FightView(discord.ui.View):
    def __init__(self, user_data, monster, on_win=None, on_lose=None):
        super().__init__(timeout=60)
        self.user = user_data
        self.monster = monster
        self.on_win = on_win
        self.on_lose = on_lose
        # Local HP copy for fight simulation (DB updated only on end_fight)
        self.user_hp = user_data['hp']
        self.monster_hp = monster['hp']

    @discord.ui.button(label="⚔️ Atakuj", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        embed = discord.Embed(title=f"Walka z {self.monster['name']}", color=0xe74c3c)
        embed.add_field(name="❤️ Twoje HP", value=f"{self.user_hp}/{self.user['max_hp']}")
        embed.add_field(name="👾 HP Potwora", value=f"{self.monster_hp}/{self.monster['hp']}")
        embed.set_footer(text=log_msg)
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_fight(self, interaction, win):
        # Fetch current user state from DB to ensure no stale exp values
        current_user = await get_user(self.user['discord_id'])
        
        if win:
            gold = self.monster['gold']
            exp = 20
            await update_user_after_fight(self.user['discord_id'], self.user_hp, current_user['exp'] + exp, gold, current_user['stamina'] - 10)
            msg = f"🏆 Wygrana! Zdobywasz {gold} złota i {exp} EXP."
            if self.on_win:
                await self.on_win(interaction)
                return
        else:
            # Loss: no EXP gain, use current DB value unchanged to prevent stale exp inflation
            await update_user_after_fight(self.user['discord_id'], 20, current_user['exp'], 0, current_user['stamina'] - 10)
            msg = "💀 Przegrałeś! Twoje HP spadło do 20."
            if self.on_lose:
                await self.on_lose(interaction)
                return

        embed = discord.Embed(title="Koniec walki", description=msg, color=0x2ecc71 if win else 0x000000)
        await interaction.response.edit_message(embed=embed, view=None)