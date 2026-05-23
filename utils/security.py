import discord
from utils.containers import message_view


async def ensure_view_owner(interaction: discord.Interaction, owner_id: str, command_hint: str = "/game") -> bool:
    """Zwraca True tylko wtedy, gdy klikający jest właścicielem widoku."""
    if str(interaction.user.id) == str(owner_id):
        return True

    text = (
        "⛔ To nie jest Twoja postać.\n"
        "Nie możesz wybierać misji, anulować wyprawy ani walczyć za innego gracza.\n"
        f"Użyj `{command_hint}`, żeby grać na swojej postaci."
    )

    view = message_view(text, 0xE74C3C)

    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)

    return False
