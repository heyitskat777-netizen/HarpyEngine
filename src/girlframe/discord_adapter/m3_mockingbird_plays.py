"""Source-owned conversation declarations and actual participant responses."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird_state import PERSON
from girlframe.services.m2_game import GameService
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.onboarding import WorkflowError

LABELS = dict(
    words="Human words",
    sentences="Normal sentence structure",
    body_language="Fluid body language",
    expressions="Correct facial expressions",
    eye_contact="Polite eye contact",
    deception="Deception",
)


async def open_book(
    interaction: discord.Interaction, game: GameService, *, actor_ref: ActorRef
) -> None:
    service = MockingbirdService(game)
    if interaction.channel_id is None:
        raise WorkflowError("Use your actual source scene channel")
    channel = interaction.channel_id
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), channel, actor_ref
    )
    if not data["plays"]:
        raise WorkflowError("No actual owned Mockingbird Play has a reviewed source release yet")
    fields = [
        Field(
            "play",
            "Choose your actual owned Play",
            tuple(
                (
                    x,
                    (
                        "Bad at Being a Person — your one-use lesson"
                        if data.get("learned_person", False)
                        else "Bad at Being a Person"
                    )
                    if x == PERSON
                    else "Sex Play",
                )
                for x in data["plays"]
            ),
        ),
        Field(
            "targets",
            "Actual conversation or interaction counterparts",
            tuple((x["token"], x["label"]) for x in data["targets"]),
            minimum=1,
            maximum=max(1, len(data["targets"])),
        ),
        Field(
            "primary",
            "For group Sex Play: actual primary counterpart",
            tuple((x["token"], x["label"]) for x in data["targets"]),
            minimum=0,
            required=False,
        ),
        Field("account", "Describe the actual printed trigger", paragraph=True),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        targets = {x["token"]: x for x in data["targets"]}
        result = await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor_ref,
            values["play"][0],
            tuple(ActorRef.model_validate(targets[x]["ref"]) for x in values["targets"]),
            values["account"],
            primary=ActorRef.model_validate(targets[values["primary"][0]]["ref"])
            if values.get("primary")
            else None,
        )
        return (
            "Actual trigger saved: "
            + str(result["id"])
            + ". Reopen your requests to confirm the roll or actual counterpart facts."
        )

    await NativeForm(
        interaction.user.id,
        "Mockingbird Plays",
        "Use the actual owned rule and actual people. "
        "A factual declaration never invents consent or another character's actions. "
        + (
            "Your lesson's actual roll uses your own resources and spends its one use."
            if data.get("learned_person", False)
            else ""
        ),
        fields,
        submit,
    ).present(interaction)


async def open_request(
    interaction: discord.Interaction,
    service: MockingbirdService,
    identity: str,
    *,
    continue_source: bool = False,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if (
        data["kind"] == "mockingbird_trigger"
        and data["owner"]
        and not data["action"]
        and data["body"]["state"] in ("ready", "proposed")
        and not continue_source
    ):
        from girlframe.discord_adapter.m3_punishments import Picker

        async def choose_source(current: discord.Interaction, token: str) -> None:
            if token == "withdraw":
                await asyncio.to_thread(
                    service.withdraw, viewer_from_interaction(current), str(current.id), identity
                )
                await reply(
                    current,
                    "Your unrolled technical proposal was withdrawn; "
                    "no fictional answer or consent was recorded.",
                )
            else:
                await open_request(current, service, identity, continue_source=True)

        await Picker(
            viewer.user_id,
            "Your actual source proposal",
            (
                ("continue", "Review source and actual owned choices"),
                ("withdraw", "Withdraw unrolled proposal"),
            ),
            choose_source,
        ).show(interaction)
        return
    body = data["body"]
    if data["kind"] == "mockingbird_conversation":
        if body["ended_event"]:
            await reply(interaction, "This actual conversation has ended.")
            return
        if data["owner"]:
            own_parties = [x for x in body["counterparts"] if x["controller"] == viewer.user_id]

            async def end(current: discord.Interaction, values: dict[str, Any]) -> str:
                operation = values["end"][0]
                if operation != "yes":
                    decision, index = operation.split(":")
                    await asyncio.to_thread(
                        service.release,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        ActorRef.model_validate(own_parties[int(index)]["actor"]),
                        decision == "allow",
                    )
                    return "Your actual interlocutor role's departure permission is saved."
                await asyncio.to_thread(
                    service.end,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    ActorRef.model_validate(data["current_actor"]),
                )
                return "This actual conversation has ended."

            await NativeForm(
                viewer.user_id,
                "Your actual conversation",
                "Available capabilities: "
                + ", ".join(LABELS[x] for x in body["allowed"])
                + ". You may not explain what you mean out of character. "
                + (
                    "Each original interlocutor must permit departure before you end it. "
                    if body["low"]
                    else ""
                )
                + "OOC safety and withdrawal remain available.",
                [
                    Field(
                        "end",
                        "Choose your actual role's action",
                        (("yes", "End conversation as the speaker"),)
                        + tuple(
                            (
                                decision + ":" + str(i),
                                label
                                + " as "
                                + data["party_labels"][
                                    ActorRef.model_validate(party["actor"]).token
                                ],
                            )
                            for i, party in enumerate(own_parties)
                            for decision, label in (
                                ("allow", "Allow departure"),
                                ("refuse", "Refuse departure"),
                            )
                        )
                        if body["low"]
                        else (("yes", "End conversation as the speaker"),),
                    )
                ],
                end,
            ).present(interaction)
            return
        parties = [x for x in body["counterparts"] if x["controller"] == viewer.user_id]
        if not body["low"] or not parties:
            await reply(
                interaction,
                "Actual conversation capabilities: "
                + ", ".join(LABELS[x] for x in body["allowed"])
                + ". You may not explain what you mean out of character. "
                + ("The original interlocutors must allow departure." if body["low"] else ""),
            )
            return
        fields = [
            Field(
                "party",
                "Your actual interlocutor role",
                tuple(
                    (
                        str(i),
                        data["party_labels"][ActorRef.model_validate(x["actor"]).token],
                    )
                    for i, x in enumerate(parties)
                ),
            ),
            Field(
                "allow",
                "Allow departure from this actual conversation?",
                (("yes", "Allow"), ("no", "Refuse")),
            ),
        ]

        async def release(current: discord.Interaction, values: dict[str, Any]) -> str:
            party = ActorRef.model_validate(parties[int(values["party"][0])]["actor"])
            await asyncio.to_thread(
                service.release,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                party,
                values["allow"][0] == "yes",
            )
            return "Your actual departure permission is saved."

        await NativeForm(
            viewer.user_id,
            "Actual conversation permission",
            "Only your original fictional role owns this permission. "
            "OOC safety and withdrawal remain available.",
            fields,
            release,
        ).present(interaction)
        return
    if data["action"]:
        await reply(
            interaction,
            (
                "Actual learned conversation source:\n" + body["account"] + "\n"
                if body.get("learned_source")
                else ""
            )
            + "This source already has Play "
            + data["action"]
            + ". Resume its pending decisions.",
        )
        return
    if body["state"] == "ready" and data["owner"]:
        actor = ActorRef.model_validate(body["actor"])
        channel = body["channel"]
        fresh = await asyncio.to_thread(service.preview, viewer, channel, actor)
        from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
        from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
        from girlframe.services.m3_dampener import DampenerService

        dampener_controls = await dampener_fields(interaction, DampenerService(service.game), actor)
        if body.get("learned_source") and not fresh.get("learned_person", False):
            raise WorkflowError("Reopen this exact available lesson or resume its actual Play")
        fields = [
            Field(
                "heat",
                "Spend your actual Heat",
                tuple((str(x), str(x)) for x in range(fresh["heat"] + 1)),
            ),
            Field(
                "identity",
                "Optional actual Identity to mark",
                tuple(
                    (x["id"], x.get("label", x.get("name", "Actual Identity")))
                    for x in fresh["identities"]
                ),
                minimum=0,
                required=False,
            ),
            Field("gain", "Identity Heat gained", tuple((str(x), str(x)) for x in range(6))),
        ] + dampener_controls

        async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
            prepared = PlayInput(
                play=body["play"],
                context=body["account"],
                trigger_confirmed=True,
                heat=int(values["heat"][0]),
                dampener_modifier=dampener_modifier(values),
                identity=values["identity"][0] if values.get("identity") else None,
                gain=int(values["gain"][0]),
                source_work=identity,
            )
            who = viewer_from_interaction(current)
            if actor.kind == "pilot":
                result = await asyncio.to_thread(
                    service.game.begin,
                    who,
                    str(current.id),
                    channel,
                    fresh["sheet_revision"],
                    prepared,
                )
            else:
                from girlframe.services.m3_actor_plays import ActorPlayService

                actual = ActorPlayService(service.game)
                view = await asyncio.to_thread(actual.preview, who, channel, actor)
                result = await asyncio.to_thread(
                    actual.begin,
                    who,
                    str(current.id),
                    channel,
                    actor,
                    view["actor"]["source_sha256"],
                    ActorRef.model_validate(view["adjudicator"]["ref"])
                    if view["adjudicator"]["ref"]
                    else None,
                    view["cast_revision"],
                    prepared,
                )
            return (
                "Actual Play prepared: "
                + str(result["action_id"])
                + ". Confirm its known roll through pending decisions."
            )

        await NativeForm(
            viewer.user_id,
            "Confirm your actual Mockingbird roll",
            "The source trigger and counterparts are frozen. "
            "Spend only this original role's actual resources.",
            fields,
            start,
        ).present(interaction)
        return
    parties = [
        x
        for x in body["parties"]
        if x["controller"] == viewer.user_id and x["decision"] == "pending"
    ]
    if not parties:
        await reply(
            interaction,
            "Waiting for actual source participants. No answer is supplied automatically.",
        )
        return
    fields = [
        Field(
            "party",
            "Your actual counterpart role",
            tuple(
                (str(i), x.get("label") or "Original counterpart role " + str(i + 1))
                for i, x in enumerate(parties)
            ),
        ),
        Field(
            "accept",
            "Confirm this factual trigger applies to this actual role?",
            (("yes", "Confirm actual trigger"), ("no", "Decline factual declaration")),
        ),
    ]

    async def attest(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.attest,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            ActorRef.model_validate(parties[int(values["party"][0])]["actor"]),
            values["accept"][0] == "yes",
        )
        return "Your actual original role's factual response is saved."

    await NativeForm(
        viewer.user_id, "Actual participant trigger review", body["account"], fields, attest
    ).present(interaction)


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["mockingbird_play"]
    if data["kind"].startswith("mockingbird_sex_") or data["kind"] in (
        "mockingbird_handler_void",
        "mockingbird_handler_girl_void",
        "mockingbird_redirect_handler_void",
        "mockingbird_redirect_handler_girl_void",
    ):
        from girlframe.discord_adapter.m3_mockingbird_sex import open_sex

        await open_sex(interaction, game, identity)
        return
    kind = data["kind"]
    if kind == "mockingbird_person_capabilities":
        fields = [
            Field(
                "options",
                "Choose the printed capabilities you can use",
                tuple((x, LABELS[x]) for x in detail["capabilities"]),
                minimum=detail["minimum"],
                maximum=detail["maximum"],
                required=bool(detail["minimum"]),
            )
        ]
    elif kind == "mockingbird_person_tag":
        fields = [
            Field(
                "tag",
                "Actual Tag based on unavailable: "
                + ", ".join(LABELS[x] for x in detail["unavailable"]),
                paragraph=True,
            )
        ]
    else:
        fields = [
            Field(
                "accept",
                "Accept this exact shared Tag?",
                (("yes", "Accept"), ("no", "Reject"))
                if kind == "mockingbird_person_agreement"
                else (("yes", "Commit agreed Tag"),),
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        answer = (
            ChoiceAnswer(options=tuple(values.get("options", ())))
            if kind == "mockingbird_person_capabilities"
            else ChoiceAnswer(text=values["tag"])
            if kind == "mockingbird_person_tag"
            else ChoiceAnswer(flag=values["accept"][0] == "yes")
        )
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Actual conversation response saved. Play: " + str(result["state"]) + "."

    await NativeForm(
        interaction.user.id,
        "Actual conversation choices",
        "You may not explain what you mean out of character. "
        + detail.get("proposed_tag", "")
        + (
            " Always available while addressing the actual Starry-Eyed counterpart: "
            + "; ".join(
                ", ".join(LABELS[x] for x in values)
                for values in detail.get("extras", {}).values()
                if values
            )
            if any(detail.get("extras", {}).values())
            else ""
        ),
        fields,
        submit,
    ).present(interaction)
