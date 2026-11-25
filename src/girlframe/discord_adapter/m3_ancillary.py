"""The original invited controller builds or declines their optional character."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_ancillary as rules
from girlframe.engine.creation_catalog import CATALOG
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService


async def open_offer(
    interaction: discord.Interaction, service: AncillaryService, options: dict[str, Any]
) -> None:
    viewer = viewer_from_interaction(interaction)
    roles = NpcRoleService(WorldService(service.missions))
    members = (await asyncio.to_thread(roles.members, viewer))["members"]
    if not members:
        await reply(
            interaction, "Invite a joined member before setting up their optional character."
        )
        return
    sites = options["sites"]
    contacts = {ref.token: ref for ref, _ in options["contacts"]}
    fields = [
        Field("controller", "Invited participant", members),
        Field(
            "site",
            "Actual starting site and faction",
            tuple((str(index), label) for index, (_, _, label) in enumerate(sites)),
        ),
    ]
    candidates = {ref.token: ref for ref, _ in options.get("candidates", ())}
    if candidates:
        fields.append(
            Field(
                "candidate",
                "Existing Pilot Candidate, if any",
                tuple((ref.token, label) for ref, label in options["candidates"]),
                minimum=0,
                required=False,
            )
        )
    if contacts:
        fields.append(
            Field(
                "contacts",
                "Contacts to disclose to this participant",
                tuple((ref.token, name) for ref, name in options["contacts"]),
                minimum=0,
                maximum=min(20, len(contacts)),
                required=False,
            )
        )

    async def send(current: discord.Interaction, values: dict[str, Any]) -> str:
        site, faction, _ = sites[int(values["site"][0])]
        await asyncio.to_thread(
            service.invite,
            viewer_from_interaction(current),
            str(current.id),
            options["revision"],
            int(values["controller"][0]),
            site,
            faction,
            tuple(contacts[x] for x in values.get("contacts", ())),
            candidate=candidates[values["candidate"][0]] if values.get("candidate") else None,
        )
        return "The original participant has a private Ancillary invitation."

    await NativeForm(
        viewer.user_id,
        "Invite an Ancillary character",
        "The original participant chooses the book and Assets in their Inbox.",
        fields,
        send,
    ).present(interaction)


async def open_invitation(
    interaction: discord.Interaction, service: AncillaryService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    value, revision = await asyncio.to_thread(service.invitation, viewer, identity)
    if value.phase != "offered":
        await reply(interaction, "Your original decision is saved.")
        return

    async def submit(current: discord.Interaction, draft: rules.Draft | None) -> str:
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            revision,
            draft,
        )
        return (
            "Your character is ready in the roles menu."
            if result["phase"] == "accepted"
            else "The invitation is declined."
        )

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        book: rules.Book = values["book"][0]
        if values["book"][0] == "decline":
            return await submit(current, None)
        contacts = await asyncio.to_thread(service.draft_targets, viewer, identity, book)
        if (book not in ("CHAINED DARLING", "WARBOY") and not contacts["bond"]) or (
            book == "MERCENARY" and not contacts["patron"]
        ):
            return "This playbook needs an eligible disclosed contact on the invitation."
        sources = (
            ("SOLDIER_3",)
            if book == "SOLDIER"
            else tuple(name for name, data in CATALOG.items() if data["family"] == "frame")
        )
        asset_choices = [(x, x) for x in rules.STARTERS[book].assets]

        async def select_assets(choose_click: discord.Interaction, picked: dict[str, Any]) -> None:
            frame = picked["catalogue"][0]
            girls = picked["girl_assets"]
            optional_fields = [
                Field("name", "Character name") if value.candidate_name is None else None,
                Field(
                    "frame_assets",
                    "Choose two Frame Assets",
                    tuple((x, x) for x in rules.frame_assets(book, frame)),
                    2,
                    2,
                ),
                Field("girl_1", "Describe " + girls[0], paragraph=True),
                Field("girl_2", "Describe " + girls[1], paragraph=True),
                Field("frame_1", "Describe the first selected Frame Asset", paragraph=True),
                Field("frame_2", "Describe the second selected Frame Asset", paragraph=True),
            ]
            fields = [item for item in optional_fields if item is not None]
            choices = {}
            for kind, label in (
                ("bond", "Starting Bond"),
                ("patron", "Patron"),
                ("wanted", "Specific Girl, if any"),
            ):
                targets = contacts[kind]
                if targets:
                    choices[kind] = {ref.token: ref for ref, _ in targets}
                    fields.append(
                        Field(
                            kind,
                            label,
                            tuple((ref.token, name) for ref, name in targets),
                            minimum=0 if kind == "wanted" else 1,
                            required=kind != "wanted",
                        )
                    )

            async def finalize(done: discord.Interaction, details: dict[str, Any]) -> str:
                frame_choices = details["frame_assets"]
                pointers = {
                    kind: targets[details[kind][0]]
                    for kind, targets in choices.items()
                    if details.get(kind)
                }
                draft = rules.Draft(
                    name=value.candidate_name or details["name"],
                    book=book,
                    frame_catalogue=frame,
                    girl_assets=(
                        rules.NamedAsset(name=girls[0], description=details["girl_1"]),
                        rules.NamedAsset(name=girls[1], description=details["girl_2"]),
                    ),
                    frame_assets=(
                        rules.NamedAsset(name=frame_choices[0], description=details["frame_1"]),
                        rules.NamedAsset(name=frame_choices[1], description=details["frame_2"]),
                    ),
                    **pointers,
                )
                return await submit(done, draft)

            await NativeForm(
                viewer.user_id,
                "Finish your Ancillary character",
                "Confirm your chosen Assets and starting contacts.",
                fields,
                finalize,
            ).present(choose_click)

        await NativeForm(
            viewer.user_id,
            "Choose starting Assets",
            "Pick the sources for your character.",
            [
                Field("girl_assets", "Choose two Girl Assets", tuple(asset_choices), 2, 2),
                Field("catalogue", "Frame Asset catalogue", tuple((x, x) for x in sources)),
            ],
            select_assets,
        ).present(current)
        return None

    await NativeForm(
        viewer.user_id,
        "Ancillary invitation",
        "Choose your book or decline this invitation."
        if value.candidate_name is None
        else "Continue as your original Pilot Candidate, " + value.candidate_name + ".",
        [
            Field(
                "book",
                "Your choice",
                (*tuple((x, x.title()) for x in value.books), ("decline", "Decline")),
            )
        ],
        choose,
    ).present(interaction)
