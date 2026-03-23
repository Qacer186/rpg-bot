import discord
import random
from database.db import update_user_after_fight, get_equipped_bonuses

class FightView(discord.ui.View):
    def __init__(self, user_data, monster):
        super().__init__(timeout=60)
        self.user = user_data
        self.monster = monster
        # Kopiujemy dane do walki, żeby nie zmieniać bazy przy każdym kliknięciu
        self.user_hp = user_data['hp']
        self.monster_hp = monster['hp']

    @discord.ui.button(label="⚔️ Atakuj", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Pobieramy bonusy z założonego ekwipunku (centralna logika w database/db.py)
        bonuses = await get_equipped_bonuses(self.user['discord_id'])

        # Obsługa przypadku, gdy SUM zwraca None (brak przedmiotów)
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        # 2. Atak gracza: baza + bonus z broni +/- losowość
        dmg = random.randint(
            self.user['attack'] + atk_bonus - 2, 
            self.user['attack'] + atk_bonus + 5
        )
        self.monster_hp -= dmg
        log_msg = f"Zadałeś **{dmg}** obrażeń potworowi {self.monster['name']}!"

        # Sprawdzenie, czy potwór padł
        if self.monster_hp <= 0:
            await self.end_fight(interaction, True)
            return

        # 3. Odwet potwora: jego atak - (Twoja obrona + bonus z pancerza)
        # max(0, ...) sprawia, że obrażenia nie mogą być ujemne (leczenie)
        m_dmg = max(0, self.monster['attack'] - (self.user['defense'] + def_bonus))
        self.user_hp -= m_dmg
        log_msg += f"\nPotwór oddaje za **{m_dmg}**!"

        # Sprawdzenie, czy gracz padł
        if self.user_hp <= 0:
            await self.end_fight(interaction, False)
            return

        # 4. Aktualizacja embeda walki
        await self.update_message(interaction, log_msg)

    async def update_message(self, interaction, log_msg):
        embed = discord.Embed(title=f"Walka z {self.monster['name']}", color=0xe74c3c)
        embed.add_field(name="❤️ Twoje HP", value=f"{self.user_hp}/{self.user['max_hp']}")
        embed.add_field(name="👾 HP Potwora", value=f"{self.monster_hp}/{self.monster['hp']}")
        embed.set_footer(text=log_msg)
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_fight(self, interaction, win):
        if win:
            gold = self.monster['gold']
            exp = 20
            await update_user_after_fight(self.user['discord_id'], self.user_hp, self.user['exp'] + exp, gold, self.user['stamina'] - 10)
            msg = f"🏆 Wygrana! Zdobywasz {gold} złota i {exp} EXP."
        else:
            await update_user_after_fight(self.user['discord_id'], 20, self.user['exp'], 0, self.user['stamina'] - 10)
            msg = "💀 Przegrałeś! Twoje HP spadło do 20."

        embed = discord.Embed(title="Koniec walki", description=msg, color=0x2ecc71 if win else 0x000000)
        await interaction.response.edit_message(embed=embed, view=None)