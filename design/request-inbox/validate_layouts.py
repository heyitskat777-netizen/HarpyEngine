"""Offline construction proof for the three native Discord mockup layouts."""

import asyncio
import json
from pathlib import Path

import discord

ROOT = Path(__file__).parent


def option_menu(placeholder: str, row: int | None = None) -> discord.ui.Select:
    return discord.ui.Select(
        placeholder=placeholder,
        row=row,
        options=[discord.SelectOption(label="Synthetic request", value="demo")],
    )


def button(label: str, row: int | None = None) -> discord.ui.Button:
    return discord.ui.Button(label=label, row=row)


def count_components(components: list[dict]) -> int:
    total = 0
    for component in components:
        total += 1
        total += count_components(component.get("components", []))
        if component.get("accessory"):
            total += count_components([component["accessory"]])
    return total


async def main() -> None:
    inbox = discord.ui.View(timeout=600)
    for label in ("Pending", "Needs you", "Waiting", "History"):
        inbox.add_item(button(label, 0))
    inbox.add_item(option_menu("All request types", 1))
    inbox.add_item(option_menu("Choose a request", 2))
    for label in ("Previous", "Next", "Refresh", "Close"):
        inbox.add_item(button(label, 3))
    guided = discord.ui.View(timeout=600)
    for label in ("Pending", "Needs you", "Waiting", "History"):
        guided.add_item(button(label, 0))
    guided.add_item(option_menu("All request types", 1))
    for label in ("Accept Bond", "Decline", "Back to inbox"):
        guided.add_item(button(label, 2))
    for label in ("Previous request", "Next request", "Refresh", "Close"):
        guided.add_item(button(label, 3))
    cards = discord.ui.LayoutView(timeout=600)
    cards.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("## Your requests\n6 need you · 2 waiting on others"),
            accent_colour=0x9F96FF,
        )
    )
    cards.add_item(
        discord.ui.ActionRow(*(button(x) for x in ("Pending", "Needs you", "Waiting", "History")))
    )
    cards.add_item(discord.ui.ActionRow(option_menu("All request types")))
    for title in ("Starting Bond", "Red Queen's Court", "Mentor agreement"):
        cards.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    f"### {title}",
                    "Synthetic task. Review before making a choice.",
                    accessory=button("Review"),
                ),
                accent_colour=0x9F96FF,
            )
        )
    cards.add_item(
        discord.ui.ActionRow(*(button(x) for x in ("Previous", "Next", "Refresh", "Close")))
    )
    embed = discord.Embed(
        title="Your requests", description="Synthetic pending request overview", colour=0x9F96FF
    )
    for label, count in (("Pending", "8"), ("Needs you", "6"), ("Waiting", "2")):
        embed.add_field(name=label, value=f"**{count}**", inline=True)
    result = {}
    for name, view in (("inbox", inbox), ("guided", guided), ("cards_v2", cards)):
        payload = view.to_components()
        count = count_components(payload)
        if name == "cards_v2":
            assert count <= 40
        else:
            assert len(payload) <= 5
            assert all(len(row["components"]) <= 5 for row in payload)
        result[name] = {"component_count": count, "components": payload}
        print(f"{name}: native SDK construction PASS; {count} component nodes")
    result["classic_embed"] = embed.to_dict()
    (ROOT / "native-components.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
