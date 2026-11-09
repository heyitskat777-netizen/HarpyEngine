"""Private voluntary source and actual owned Princess intimacy decisions."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError

DISCLOSURE = (
    "Confirm only your own actual voluntary interaction. On a high result the Princess "
    "chooses one immediately required Play and makes every actor-owned decision for you "
    "during that Play, including the necessary decision fields. Other people's decisions "
    "and safety controls remain theirs. No reply or further consent is inferred."
)


async def open_princess(
    interaction: discord.Interaction,
    service: SexService,
    identity: str | None = None,
    *,
    learned_source: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, channel)
        if learned_source is not None and learned_source not in {x["id"] for x in data["lessons"]}:
            raise WorkflowError("Reopen your actual available learned source")
        options = [("invite", "Propose your actual voluntary source")] if data["targets"] else []
        options += [(x["id"], "Saved interaction: " + x["phase"]) for x in data["sessions"]]
        if not options:
            await reply(interaction, "No supported current Princess interaction in this scene.")
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = values["action"][0]
            if selected != "invite":
                await open_princess(current, service, selected)
                return None

            async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = next(x for x in data["targets"] if x["token"] == answer["target"][0])
                await asyncio.to_thread(
                    service.invite,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ActorRef.model_validate(target["ref"]),
                    data["revision"],
                    answer["account"],
                    learned_source=next(iter(answer.get("lesson", ())), learned_source),
                )
                return "Saved. The actual counterpart answers their own private source invitation."

            form = NativeForm(
                current.user.id,
                "Princess source",
                DISCLOSURE,
                [
                    Field(
                        "target",
                        "Actual original counterpart",
                        tuple((x["token"], x["label"]) for x in data["targets"]),
                    ),
                    Field("account", "Your actual voluntary source interaction", paragraph=True),
                ]
                + (
                    [
                        Field(
                            "lesson",
                            "One actual lesson for this voluntary source",
                            tuple((x["id"], x["label"]) for x in data["lessons"]),
                        )
                    ]
                    if data["lessons"]
                    else []
                ),
                invite,
            )
            if learned_source is not None:
                form.values["lesson"] = (learned_source,)
            await form.present(current)
            return None

        await NativeForm(
            viewer.user_id,
            "Princess controls",
            DISCLOSURE,
            [Field("action", "Owned source", tuple(options))],
            choose,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data.get("lesson_cancelled"):
        await reply(
            interaction,
            "You cancelled this unrolled learned source. Its lesson is unused; "
            "a new source needs a new invitation and the actual counterpart's own answer.",
        )
        return
    if data["phase"] == "invited" and data["counterpart"] == viewer.user_id:

        async def confirm(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.confirm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["accept"][0] == "yes",
                values["account"],
            )
            return "Your own disclosed source response is saved."

        await NativeForm(
            viewer.user_id,
            "Your Princess source answer",
            DISCLOSURE + " Proposed source: " + data["proposal"],
            [
                Field(
                    "accept",
                    "Your actual voluntary source",
                    (("yes", "Confirm"), ("no", "Decline")),
                ),
                Field("account", "Your own actual answer", paragraph=True),
            ],
            confirm,
        ).present(interaction)
        return
    if data["phase"] == "accepted" and data["caster"] == viewer.user_id:
        sheet = await asyncio.to_thread(service.game.sheet, viewer)

        async def begin(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(current),
                str(current.id),
                channel,
                sheet["revision"],
                PlayInput(
                    play=rules.PLAY,
                    target_actor=ActorRef.model_validate(data["target"]),
                    source_work=identity,
                    context=values["context"],
                    trigger_confirmed=True,
                    heat=int(values["heat"][0]),
                    kicked_puppy_basis=bool(values.get("kicked_puppy_basis")),
                    dampener_modifier=cast(Literal[2, 3], int(values["dampener_modifier"][0]))
                    if values.get("dampener_modifier")
                    else None,
                    identity=next(iter(values.get("identity", ())), None),
                    gain=int(values.get("gain", ("0",))[0]),
                ),
            )
            return "Actual original Play prepared. Continue its saved choices. " + str(
                result["action_id"]
            )

        heat = sheet["heat"]
        await NativeForm(
            viewer.user_id,
            "Prepare Princess Sex Play",
            DISCLOSURE,
            [
                Field("context", "Your actual confirmed interaction", paragraph=True),
                Field(
                    "identity",
                    "Optional own Identity to mark",
                    tuple((x["id"], x["name"]) for x in sheet["identities"] if not x["marked"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "gain", "Actual Identity Heat gained", tuple((str(n), str(n)) for n in range(6))
                ),
                Field(
                    "heat",
                    "Heat to spend",
                    tuple((str(n), str(n)) for n in range(heat + 6)),
                ),
            ],
            begin,
        ).present(interaction)
        return
    choices = await asyncio.to_thread(service.game.choices, viewer)
    row = next(
        (
            x
            for x in choices
            if x["kind"] == "princess_sex_child" and x["action_id"] == data["action"]
        ),
        None,
    )
    if row:
        await open_choice(interaction, service.game, row["id"])
        return
    await reply(
        interaction,
        "Saved private Princess interaction: "
        + data["phase"]
        + ". Continue your actual owned decisions in Play controls or Inbox.",
    )


async def open_choice(
    interaction: discord.Interaction,
    game: GameService,
    identity: str,
    *,
    _dose_resources: bool = False,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    kind, detail = data["kind"], data["princess_sex"]
    service = SexService(game)
    source = await asyncio.to_thread(service.view, viewer, detail["session"])
    if kind == "princess_sex_child":
        child = source["child"]
        if child["play"] == "dose_up" and not _dose_resources:
            from girlframe.discord_adapter.m3_dose_up import open_controlled_dose
            from girlframe.services.m3_dose_up import DoseUpService

            await open_controlled_dose(
                interaction, DoseUpService(game.store, game), child["direction"]
            )
            return
        if child["child"]:
            from girlframe.discord_adapter.m2_ui import open_pending

            await open_pending(interaction, game)
            return
        if child["play"] == "all_out_assault":
            from girlframe.discord_adapter.m3_battle import open_declaration
            from girlframe.services.m3_battle import BattleService

            await open_declaration(
                interaction, BattleService(game.store), parent=child["descriptor"]
            )
            return
        nightmare = (
            {"owned": True} if child["nightmare"] and child["play"] == "keep_your_head" else None
        )
        fields = [
            Field(
                "heat",
                "Actual counterpart Heat to spend",
                tuple((str(n), str(n)) for n in ((0,) if nightmare else range(child["heat"] + 6))),
            )
        ]
        fields += [
            Field(
                "identity",
                "Optional actual Identity to mark",
                tuple(
                    (x["id"], x["name"])
                    for x in child["identities"] + child["additional_identities"]
                ),
                minimum=0,
                required=False,
            ),
            Field("gain", "Actual Identity Heat gained", tuple((str(n), str(n)) for n in range(6))),
            Field(
                "pair_share",
                "Only Paired: actual Heat given to the Pair",
                tuple((str(n), str(n)) for n in range(6)),
                minimum=0,
                required=False,
            ),
        ]
        if child["kicked_puppy"]:
            fields.append(
                Field(
                    "kicked_puppy_basis",
                    "Counterpart's paid Kicked Puppy roll basis",
                    (("damaged", "Actual damaged Girl Assets; spend no Heat"),),
                    minimum=0,
                    required=False,
                )
            )
        if child["dampener"]:
            fields.append(
                Field(
                    "dampener_modifier",
                    "Counterpart's paid Dampener: spend at least 5 Heat",
                    (("2", "+2 basis"), ("3", "+3 basis")),
                    minimum=0,
                    required=False,
                )
            )
        if child["disposable"]:
            fields.append(
                Field(
                    "disposable_heat",
                    "Disposable Psyche: remove the actual marked Identity for extra Heat",
                    (("0", "Do not remove"), ("3", "Remove for +3"), ("4", "Remove for +4")),
                    minimum=0,
                    required=False,
                )
            )
        if child["play"] == "disobey_orders":
            fields.append(
                Field(
                    "witnessed",
                    "Actual Foundation witness to this refusal",
                    (("yes", "Actually witnessed"), ("no", "Not witnessed")),
                )
            )
    elif kind == "princess_sex_direct":
        fields = [
            Field(
                "play",
                "Immediately required supported Play",
                tuple((x["id"], x["label"]) for x in detail["plays"]),
            ),
            Field("text", "Actual legal trigger and immediate action", paragraph=True),
        ]
        if detail["targets"]:
            fields.append(
                Field(
                    "target",
                    "If this Play needs a target: actual original scene actor",
                    tuple((x["token"], x["label"]) for x in detail["targets"]),
                    minimum=0,
                    required=False,
                )
            )
        if detail["orders"]:
            fields.append(
                Field(
                    "order_id",
                    "Disobey only: actual already-received Order",
                    tuple((x["id"], x["label"]) for x in detail["orders"]),
                    minimum=0,
                    required=False,
                )
            )
    elif kind == "princess_sex_favour_reply":
        fields = [
            Field(
                "options",
                "Your own actual favour response",
                (("agree", "Agree"), ("refuse", "Refuse")),
            ),
            Field("text", "Your own actual response", paragraph=True),
        ]
    elif kind == "princess_sex_optional_tag":
        fields = [
            Field(
                "options",
                "Your optional ordinary Tag",
                (("give", "Give a Tag"), ("decline", "Decline")),
            ),
            Field("text", "If giving: actual Tag", required=False),
        ]
    else:
        fields = [
            Field(
                "text",
                "Actual Tag" if kind == "princess_sex_low_tag" else "Your actual requested favour",
                paragraph=True,
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "princess_sex_child":
            result = await asyncio.to_thread(
                game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                child["sheet_revision"],
                PlayInput(
                    play=child["play"],
                    parent=child["parent"],
                    source_work=child["source_work"],
                    target=int(child["target"]["entity"])
                    if child["target"]
                    and child["target"]["kind"] == "pilot"
                    and child["play"] in ("flirt", "put_someone_beneath_you")
                    else None,
                    target_actor=ActorRef.model_validate(child["target"])
                    if child["target"]
                    and (
                        child["play"] == "engage"
                        or child["play"] == "flirt"
                        and child["target"]["kind"] == "npc"
                    )
                    else None,
                    order_id=child["order_id"],
                    piloting=bool(child["piloting"]),
                    witnessed=values.get("witnessed", ("no",))[0] == "yes",
                    pair_share=int(next(iter(values.get("pair_share", ())), "0")),
                    context=child["context"],
                    heat=int(values["heat"][0]),
                    kicked_puppy_basis=bool(values.get("kicked_puppy_basis")),
                    dampener_modifier=cast(Literal[2, 3], int(values["dampener_modifier"][0]))
                    if values.get("dampener_modifier")
                    else None,
                    identity=next(iter(values.get("identity", ())), None),
                    gain=int(values.get("gain", ("0",))[0]),
                    disposable_heat=cast(
                        Literal[0, 3, 4], int(next(iter(values.get("disposable_heat", ())), "0"))
                    ),
                    trigger_confirmed=True,
                ),
            )
            return "Actual counterpart child prepared under your one-Play authority. " + str(
                result["action_id"]
            )
        options = (
            (values["play"][0],)
            if kind == "princess_sex_direct"
            else tuple(values.get("options", ()))
        )
        text = "" if options == ("decline",) else values.get("text", "")
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(
                options=options,
                text=text,
                fields={key: values[key][0] for key in ("target", "order_id") if values.get(key)}
                if kind == "princess_sex_direct"
                else {},
            ),
        )
        return "Actual owned source decision saved."

    await NativeForm(
        viewer.user_id,
        "Controlled native Stim self-Dose"
        if kind == "princess_sex_child" and child["play"] == "dose_up"
        else "Princess: " + kind.removeprefix("princess_sex_"),
        "Actual original participants and one scoped child only. "
        + (detail["favour"] or "")
        + (
            " These are the original Stim counterpart's own Heat and Identities; "
            "your source grants its actor choices for this one actual Play."
            if kind == "princess_sex_child" and child["play"] == "dose_up"
            else ""
        ),
        fields,
        submit,
    ).present(interaction)
