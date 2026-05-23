import discord
from discord import ui


DEFAULT_COLOR = 0x5865F2


def _to_colour(value):
    if value is None:
        return None
    if isinstance(value, discord.Colour):
        return value
    return discord.Colour(value)


def _split_text(text: str, limit: int = 3900):
    text = str(text)
    if len(text) <= limit:
        return [text]

    parts = []
    current = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            parts.append("".join(current))
            current = []
            current_len = 0

        if len(line) > limit:
            while line:
                parts.append(line[:limit])
                line = line[limit:]
        else:
            current.append(line)
            current_len += len(line)

    if current:
        parts.append("".join(current))

    return parts


def make_container(text: str, accent_color: int | discord.Colour | None = DEFAULT_COLOR):
    container = ui.Container(accent_color=_to_colour(accent_color))
    parts = _split_text(text)

    for index, part in enumerate(parts):
        if index > 0:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(ui.TextDisplay(part))

    return container


def add_container(view: discord.ui.LayoutView, text: str, accent_color: int | discord.Colour | None = DEFAULT_COLOR):
    container = make_container(text, accent_color)
    view.add_item(container)
    return container


def add_separator(container: ui.Container, *, large: bool = False, visible: bool = True):
    spacing = discord.SeparatorSpacing.large if large else discord.SeparatorSpacing.small
    container.add_item(ui.Separator(visible=visible, spacing=spacing))
    return container


def add_action_row(container: ui.Container, *items: ui.Item, separator: bool = True):
    if separator:
        add_separator(container)

    row = ui.ActionRow()
    for item in items:
        row.add_item(item)

    container.add_item(row)
    return row


def message_view(text: str, accent_color: int | discord.Colour | None = DEFAULT_COLOR):
    view = discord.ui.LayoutView(timeout=None)
    add_container(view, text, accent_color)
    return view
