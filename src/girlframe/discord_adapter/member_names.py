"""Current guild display names for explicit member labels; stored IDs stay opaque."""

import asyncio
import inspect
import re
from typing import Any, cast

import discord

_TOKEN = re.compile(r"⟪member:([0-9]{1,20})⟫")
_SNOWFLAKE = re.compile(r"[0-9]{15,20}\Z")


def member_label(user_id: int | str) -> str:
    """Mark a system-authored member reference for resolution at the UI boundary."""
    value = str(user_id)
    return f"⟪member:{value}⟫" if value.isdecimal() and len(value) <= 20 else "Unavailable member"


def _display(member: Any) -> str | None:
    for attribute in ("display_name", "global_name", "name"):
        value = getattr(member, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def _cache(interaction: discord.Interaction) -> dict[int, str]:
    extras = getattr(interaction, "extras", None)
    if isinstance(extras, dict):
        return cast(dict[int, str], extras.setdefault("girlframe_member_names", {}))
    return {}


async def _name(interaction: discord.Interaction, identity: int) -> str:
    if getattr(interaction.user, "id", None) == identity:
        own = _display(interaction.user)
        if own is not None:
            return own
    guild = interaction.guild
    if guild is None:
        return "Unavailable member"
    fetch = getattr(guild, "fetch_member", None)
    if callable(fetch) and inspect.iscoroutinefunction(fetch):
        try:
            async with asyncio.timeout(3):
                member = await fetch(identity)
            name = _display(member)
            if name is not None:
                return name
        except discord.NotFound:
            return "Former member"
        except (discord.HTTPException, TimeoutError):
            pass
    get = getattr(guild, "get_member", None)
    return (_display(get(identity)) if callable(get) else None) or "Unavailable member"


async def _resolve(interaction: discord.Interaction, identities: set[int]) -> dict[int, str]:
    cache = _cache(interaction)
    gate = asyncio.Semaphore(5)

    async def one(identity: int) -> None:
        if identity not in cache:
            async with gate:
                cache[identity] = await _name(interaction, identity)

    await asyncio.gather(*(one(identity) for identity in identities))
    return cache


async def render_member_labels(
    interaction: discord.Interaction, text: str, *, markdown: bool = True
) -> str:
    """Resolve explicit UI tokens only; never reinterpret narrative or receipt digits."""
    identities = {int(x) for x in _TOKEN.findall(text)}
    if not identities:
        return text
    names = await _resolve(interaction, identities)

    def replace(match: re.Match[str]) -> str:
        name = discord.utils.escape_mentions(names[int(match.group(1))])
        return discord.utils.escape_markdown(name) if markdown else name

    return _TOKEN.sub(replace, text)


def needs_member_rendering(text: str, view: discord.ui.View | None = None) -> bool:
    if _TOKEN.search(text):
        return True
    if view is not None:
        if any(
            _TOKEN.search(value[0])
            for value in getattr(view, "_member_label_templates", {}).values()
        ):
            return True
        for item in view.children:
            if isinstance(item, discord.ui.Button) and _TOKEN.search(item.label or ""):
                return True
            if isinstance(item, discord.ui.Select) and any(
                _TOKEN.search(x.label)
                or _TOKEN.search(x.description or "")
                or _SNOWFLAKE.fullmatch(x.value)
                for x in item.options
            ):
                return True
    return False


async def render_member_view(
    interaction: discord.Interaction, view: discord.ui.View | None
) -> None:
    """Resolve visible controls without changing submitted values or custom IDs."""
    if view is None:
        return
    memory = getattr(view, "_member_label_templates", {})
    fields: list[tuple[Any, str, str, tuple[Any, ...]]] = []
    direct: list[tuple[discord.SelectOption, int]] = []
    key: tuple[Any, ...]
    for item in view.children:
        if isinstance(item, discord.ui.Select):
            if item.placeholder:
                key = (id(item), "placeholder")
                previous = memory.get(key)
                template = (
                    previous[0]
                    if previous and previous[1] == item.placeholder
                    else item.placeholder
                )
                fields.append((item, "placeholder", template, key))
            for option in item.options:
                for attribute in ("label", "description"):
                    current = getattr(option, attribute)
                    if current is None:
                        continue
                    key = (id(item), option.value, attribute)
                    previous = memory.get(key)
                    template = previous[0] if previous and previous[1] == current else current
                    fields.append((option, attribute, template, key))
                # Member selectors commonly retain opaque IDs as option values.
                if _SNOWFLAKE.fullmatch(option.value):
                    direct.append((option, int(option.value)))
        elif isinstance(item, discord.ui.Button) and item.label:
            key = (id(item), "label")
            previous = memory.get(key)
            template = previous[0] if previous and previous[1] == item.label else item.label
            fields.append((item, "label", template, key))
    identities = {int(x) for _, _, template, _ in fields for x in _TOKEN.findall(template)}
    identities.update(identity for _, identity in direct)
    names = await _resolve(interaction, identities)
    for obj, attribute, template, key in fields:
        rendered = _TOKEN.sub(
            lambda match: discord.utils.escape_mentions(names[int(match.group(1))]), template
        )
        limit = 80 if isinstance(obj, discord.ui.Button) else 100
        rendered = rendered[:limit]
        setattr(obj, attribute, rendered)
        memory[key] = (template, rendered)
    for option, identity in direct:
        if names[identity] not in ("Unavailable member", "Former member"):
            key = next(
                key for obj, attribute, _, key in fields if obj is option and attribute == "label"
            )
            original = memory[key][0]
            option.label = discord.utils.escape_mentions(names[identity])[:100]
            memory[key] = (original, option.label)
    view._member_label_templates = memory  # type: ignore[attr-defined]
