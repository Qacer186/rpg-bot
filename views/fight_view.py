import discord
import random
from discord import ui
from database.db import update_user_after_fight, get_equipped_bonuses, get_user, exp_info_line
from utils.containers import add_action_row, add_container, message_view
from utils.security import ensure_view_owner


class FightView(discord.ui.LayoutView):
    def __init__(self, user_data, monster, on_win=None, on_lose=None, gold_reward=0, exp_reward=0):
        super().__init__(timeout=None)
        self.user = user_data
        self.monster = monster
        self.on_win = on_win
        self.on_lose = on_lose
        self.gold_reward = gold_reward
        self.exp_reward = exp_reward
        self.user_hp = user_data['hp']
        self.monster_hp = monster['hp']
        self.rebuild("Kliknij **Atakuj**, aby rozpocząć walkę.")

    def rebuild(self, log_msg: str):
        self.clear_items()
        container = add_container(self, self.build_fight_text(log_msg), 0xE74C3C)
        self.setup_fight_buttons(container)

    def setup_fight_buttons(self, container):
        attack_btn = ui.Button(label="⚔️ Atakuj", style=discord.ButtonStyle.danger)
        attack_btn.callback = self.attack
        add_action_row(container, attack_btn)

    async def attack(self, interaction: discord.Interaction):
        if not await ensure_view_owner(interaction, self.user['discord_id'], "/tavern"):
            return

        await interaction.response.defer()

        bonuses = await get_equipped_bonuses(self.user['discord_id'])
        atk_bonus = bonuses['total_atk'] if bonuses and bonuses['total_atk'] else 0
        def_bonus = bonuses['total_def'] if bonuses and bonuses['total_def'] else 0

        min_dmg = max(1, self.user['attack'] + atk_bonus - 2)
        max_dmg = max(min_dmg, self.user['attack'] + atk_bonus + 5)
        dmg = random.randint(min_dmg, max_dmg)
        self.monster_hp -= dmg
        log_msg = f"Zadałeś **{dmg}** obrażeń potworowi **{self.monster['name']}**!"

        if self.monster_hp <= 0:
            await self.end_fight(interaction, True)
            return

        m_dmg = max(0, self.monster['attack'] - (self.user['defense'] + def_bonus))
        self.user_hp -= m_dmg
        log_msg += f"\nPotwór oddaje za **{m_dmg}** obrażeń."

        if self.user_hp <= 0:
            await self.end_fight(interaction, False)
            return

        self.rebuild(log_msg)
        await interaction.followup.edit_message(interaction.message.id, view=self)

    def build_fight_text(self, log_msg: str):
        player_hp_percent = self._bar_percent(self.user_hp, self.user['max_hp'])
        monster_hp_percent = self._bar_percent(self.monster_hp, self.monster['hp'])

        player_bar = "❤️" * player_hp_percent + "🖤" * (10 - player_hp_percent)
        monster_bar = "❤️" * monster_hp_percent + "🖤" * (10 - monster_hp_percent)

        return (
            f"### ⚔️ Walka z {self.monster['name']}\n"
            f"{log_msg}\n\n"
            f"**👤 Gracz**\n"
            f"HP: `{max(0, self.user_hp)}/{self.user['max_hp']}`\n"
            f"{player_bar}\n\n"
            f"**👹 {self.monster['name']}**\n"
            f"HP: `{max(0, self.monster_hp)}/{self.monster['hp']}`\n"
            f"{monster_bar}\n\n"
            "Kliknij **Atakuj**, aby kontynuować."
        )

    async def end_fight(self, interaction, win):
        current_user = await get_user(self.user['discord_id'])

        if win:
            gold = self.gold_reward
            exp = self.exp_reward
            saved_hp = max(1, min(self.user_hp, current_user['max_hp']))
            await update_user_after_fight(
                self.user['discord_id'],
                saved_hp,
                current_user['exp'] + exp,
                gold,
                max(0, current_user['stamina'] - 10)
            )

            fresh_user = await get_user(self.user['discord_id'])

            result_text = (
                "### 🏆 WYGRANA!\n"
                f"Pokonałeś **{self.monster['name']}**!\n\n"
                f"❤️ Zostało HP: `{saved_hp}/{current_user['max_hp']}`\n"
                "HP będzie odnawiało się z czasem.\n"
                f"💰 Złoto: `+{gold}`\n"
                f"✨ Doświadczenie: `+{exp} EXP`\n"
                f"{exp_info_line(fresh_user)}\n\n"
                "Powrót do karczmy..."
            )
            await interaction.followup.edit_message(interaction.message.id, view=message_view(result_text, 0x2ECC71))

            if self.on_win:
                await self.on_win(interaction)
                return
        else:
            await update_user_after_fight(
                self.user['discord_id'],
                20,
                current_user['exp'],
                0,
                max(0, current_user['stamina'] - 10)
            )

            result_text = (
                "### 💀 PRZEGRANA\n"
                f"**{self.monster['name']}** Cię pokonał...\n\n"
                "❤️ HP ustawione na `20`. Dalej odnawia się z czasem.\n"
                "💰 Złoto: `0`\n"
                "✨ EXP: `0`\n\n"
                "Obudź się w tawernie..."
            )
            await interaction.followup.edit_message(interaction.message.id, view=message_view(result_text, 0xE74C3C))

            if self.on_lose:
                await self.on_lose(interaction)
                return

    @staticmethod
    def _bar_percent(current, maximum):
        if maximum <= 0:
            return 0
        return max(0, min(10, int((current / maximum) * 10)))
