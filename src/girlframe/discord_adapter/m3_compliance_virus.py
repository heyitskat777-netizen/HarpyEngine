"""Actual source-owned cockpit/touch/purge dropdowns and original-human orders."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_compliance_virus_state import FrameRef
from girlframe.services.m3_compliance_virus import VirusService
from girlframe.services.onboarding import WorkflowError


async def open_virus(
    interaction: discord.Interaction, service: VirusService, actor: ActorRef, channel: int
) -> None:
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), channel, actor
    )
    options = []
    if data["cockpit"]:
        options.append(("infect", "Infect the actual occupied cockpit"))
    options += [("frame:" + x["id"], "Remote purge: " + x["label"]) for x in data["frames"]]
    options += [("girl:" + x["id"], "Touch purge: " + x["label"]) for x in data["people"]]
    if not options:
        await reply(
            interaction, "There is no actual occupied cockpit or source-owned infection to act on."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        token = values["operation"][0]
        if token == "infect":
            await asyncio.to_thread(
                service.infect,
                viewer_from_interaction(current),
                str(current.id),
                channel,
                actor,
                FrameRef.model_validate(data["cockpit"]),
                data["source_sha256"],
                values["account"],
            )
            return "Actual cockpit infection recorded; only actual link transitions spread it."
        kind, identity = token.split(":", 1)
        result = await asyncio.to_thread(
            service.begin_purge,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            identity,
            kind,
            values["account"],
        )
        if result["phase"] == "contact_review":
            return (
                "Actual touching proposal saved. The original source judge must review the "
                "physical fact."
            )
        return (
            "Printed fixed11 effect recorded with NO ROLL or Heat; actual immediate "
            "Punishment awaits its real owners."
        )

    form = NativeForm(
        interaction.user.id,
        "Compliance Virus",
        "Use only your actual original role and source-owned infection. Remote Frame "
        "purge creates the printed fixed11 consequence; touch purge records a real "
        "physical act, reviewed factually without inventing victim consent.",
        [
            Field("operation", "Source-owned operation", tuple(options)),
            Field("account", "Actual cockpit infection or purge action", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_purge(
    interaction: discord.Interaction, service: VirusService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["phase"] == "queued":
        await reply(
            interaction,
            "The confirmed diceless operation is waiting for its actual chat pause. "
            "No purge effect or dice have occurred.",
        )
        return
    if not data["can_act"] or data["phase"] in ("complete", "ended"):
        await reply(interaction, "This saved original source is read-only or complete.")
        return
    if data["phase"] in ("vacancy_proposal", "vacancy_review"):
        from girlframe.services.m3_virus_operations import OperationService

        options = (
            (
                ("vacant", "Frame actually has no linked Pilot"),
                ("owner_linked", "Its original assigned Pilot is actually linked"),
            )
            if data["phase"] == "vacancy_proposal"
            else (
                ("confirm", "The original factual account is confirmed"),
                ("reject", "Facts do not support the account"),
            )
        )

        async def occupancy(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                OperationService(service.game).occupancy,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["choice"][0],
                values["account"],
            )
            return (
                "Actual vacancy/source-link fact recorded; only actual effects proceed. Phase: "
                + str(result["phase"])
            )

        form = NativeForm(
            interaction.user.id,
            "Virus: actual Frame occupancy",
            "Absence of a link record proves no vacancy. Actual original Frame owner records the "
            "fact, then the frozen judge reviews. This does not create a foreign Pilot, move "
            "anyone or grant a Frame.",
            [
                Field("choice", "Actual original link fact", options),
                Field("account", "Actual facts and evidence", paragraph=True),
            ],
            occupancy,
        )
        await reply(interaction, form.text(), form)
        return
    if data["phase"] == "punishment" and data["case"]:
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(interaction, RolePunishmentService(service.game), data["case"])
        return
    if not data["can_act"] or data["phase"] in ("complete", "ended"):
        await reply(interaction, "This saved original source is read-only or complete.")
        return
    if data["phase"] == "contact_review":

        async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.review_contact,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["confirmed"][0] == "yes",
                values["account"],
            )
            return (
                "Actual touching facts recorded; only confirmed physical contact permits the "
                "source purge."
            )

        form = NativeForm(
            interaction.user.id,
            "Virus: actual touch review",
            "The original source owner proposes actual touching. Confirm or reject only "
            "that physical fact; this does not invent contact, movement or player "
            "agreement.",
            [
                Field(
                    "confirmed",
                    "Actual touching",
                    (
                        ("yes", "Actual source contact occurred"),
                        ("no", "Actual contact is not established"),
                    ),
                ),
                Field("account", "Factual source account", paragraph=True),
            ],
            review,
        )
        await reply(interaction, form.text(), form)
    elif data["phase"] == "order":

        async def order(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.issue_order,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["order"],
            )
            return (
                "Actual order recorded; this Harpy remains immune to Receive Orders."
                if result.get("immune")
                else (
                    "Actual one-shot superior order issued. "
                    "Its original recipient owns the real response."
                )
            )

        form = NativeForm(
            interaction.user.id,
            "Virus: one actual order",
            "This source grants one direct superior order without changing Status or "
            "creating general authority.",
            [Field("order", "Actual direct order", paragraph=True)],
            order,
        )
        await reply(interaction, form.text(), form)
    else:
        await reply(
            interaction,
            "Continue the actual owned order/Punishment from your source inbox. Method: "
            + data["method"],
        )


async def open_order(interaction: discord.Interaction, game: Any, data: dict[str, Any]) -> None:
    from girlframe.services.m3_actor_plays import ActorPlayService

    if data["kind"] == "order_response":

        async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                data["id"],
                data["revision"],
                ChoiceAnswer(options=(values["response"][0],)),
            )
            return "Your actual original response is saved."

        form = NativeForm(
            interaction.user.id,
            "Actual direct order",
            data["order_text"],
            [
                Field(
                    "response",
                    "Your original response",
                    (
                        ("obedient", "Obediently"),
                        ("immediate", "Immediately"),
                        ("hesitant", "Hesitantly"),
                        ("mouthing_off", "Mouthing off"),
                        ("gritted_teeth", "Through gritted teeth"),
                        ("disobey", "Disobey: begin the actual response Play"),
                    ),
                )
            ],
            respond,
        )
        await reply(interaction, form.text(), form)
        return
    if data["kind"] != "order_disobey":
        raise WorkflowError("Open only this exact actual source order response.")
    ref = ActorRef.model_validate(data["target_actor"])
    if ref.kind == "pilot":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data, _pilot=True)
        return
    service = ActorPlayService(game)
    channel = int(data.get("channel_id") or interaction.channel_id or 0)
    preview = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), channel, ref
    )
    actor = preview["actor"]
    identities = tuple((x["id"], x["name"]) for x in actor["identities"] if not x["marked"])

    async def disobey(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity = values["identity"][0]
        await asyncio.to_thread(
            service.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            ref,
            actor["source_sha256"],
            ActorRef.model_validate(preview["adjudicator"]["ref"])
            if preview["adjudicator"]["ref"]
            else None,
            preview["cast_revision"],
            PlayInput(
                play="disobey_orders",
                parent=data["action_id"],
                order_id=data["body"]["order_id"],
                context=values["account"],
                trigger_confirmed=True,
                heat=int(values["heat"]),
                identity=None if identity == "none" else identity,
                gain=0 if identity == "none" else int(values["gain"]),
                witnessed=values["witnessed"][0] == "yes",
            ),
        )
        return (
            "Actual HandlerGirl Disobey confirmed: one real Heat roll and normal table Tag "
            "procedure; no fictitious Status is created."
        )

    form = NativeForm(
        interaction.user.id,
        "Girl-rules Disobey",
        "Use your actual HandlerGirl Heat and Identities. Foundation witness is "
        "recorded, but this role has no numeric Status to lower.",
        [
            Field("heat", "Actual Heat to spend"),
            Field(
                "identity",
                "Optional actual Identity",
                (("none", "Do not mark an Identity"), *identities),
            ),
            Field("gain", "Heat gained from selected Identity (0 otherwise)"),
            Field(
                "witnessed",
                "Foundation witness",
                (("no", "Not witnessed"), ("yes", "Actual Foundation member notices")),
            ),
            Field("account", "Actual refusal", paragraph=True),
        ],
        disobey,
    )
    await reply(interaction, form.text(), form)


async def open_disobey_choice(
    interaction: discord.Interaction, game: Any, data: dict[str, Any]
) -> None:
    kind = data["kind"]
    level = data["result"]["tier"]
    if kind == "virus_disobey_punishment":
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(
            interaction, RolePunishmentService(game), data["body"]["case_id"]
        )
        return
    if kind in ("virus_disobey_follow", "virus_disobey_discovery") or level == "high":
        label = (
            "Act immediately without thinking"
            if kind == "virus_disobey_follow"
            else "Actual rules Handler discovers refusal"
            if kind == "virus_disobey_discovery"
            else "Act now without thinking"
        )
        fields = [Field("flag", label, (("yes", "Yes"), ("no", "No")))]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                data["id"],
                data["revision"],
                ChoiceAnswer(flag=values["flag"][0] == "yes"),
            )
            return "Actual owned response saved."
    else:
        fields = [
            Field(
                "option",
                "Printed mid result",
                (
                    ("tag_heat", "Give yourself a Tag and gain Heat"),
                    ("reject_tag", "Reject an actual Tag"),
                    ("follow", "Tell an actual other human to follow"),
                ),
            ),
            Field("tag", "New Tag text", required=False),
            Field(
                "existing_tag",
                "Actual Tag to reject",
                (
                    ("none", "Not rejecting a Tag"),
                    *tuple((x["id"], x["label"]) for x in data.get("tags", ())),
                ),
            ),
            Field(
                "follower",
                "Actual other role",
                (
                    ("none", "Not asking someone to follow"),
                    *tuple((x["token"], x["label"]) for x in data.get("disobey_followers", ())),
                ),
            ),
            Field("number", "Heat gain 1–2 (Tag option only)", required=False),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            option = values["option"][0]
            answer = ChoiceAnswer(
                options=(option,),
                text=values.get("tag", "") if option == "tag_heat" else "",
                number=int(values["number"]) if option == "tag_heat" else None,
                denied=(values["existing_tag"][0],) if option == "reject_tag" else (),
                fields={"follower_actor": values["follower"][0]} if option == "follow" else {},
            )
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                data["id"],
                data["revision"],
                answer,
            )
            return "Actual owned result saved."

    form = NativeForm(
        interaction.user.id,
        "Actual Disobey result",
        "Printed result, original body resources and actual human ownership apply.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_exposure_start(
    interaction: discord.Interaction, game: Any, actor: ActorRef, channel: int
) -> None:
    from girlframe.services.m3_virus_exposure import ExposureService

    service = ExposureService(game)
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), channel, actor
    )
    if not data["frames"] or not data["episodes"]:
        await reply(
            interaction,
            "No actual earlier owned episode proves an already infected Frame here. "
            "Missing chronology cannot be filled by a later infection.",
        )
        return

    async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            values["frame"][0],
            values["episode"][0],
            values["account"],
        )
        return (
            "Actual past link exposure proposed. Original Frame owner and frozen judge "
            "must separately confirm factual evidence; no current Frame/control/position changed."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual past link exposure",
        "Record an actual earlier link only. The Frame must already have been infected in that "
        "original episode; current control, resources and position stay unchanged.",
        [
            Field(
                "frame", "Actual source Frame", tuple((x["id"], x["label"]) for x in data["frames"])
            ),
            Field(
                "episode",
                "Actual earlier source episode",
                tuple((x["id"], x["label"]) for x in data["episodes"]),
            ),
            Field("account", "Actual past link and factual evidence", paragraph=True),
        ],
        propose,
    )
    await reply(interaction, form.text(), form)


async def open_exposure(interaction: discord.Interaction, game: Any, identity: str) -> None:
    from girlframe.services.m3_virus_exposure import ExposureService

    service = ExposureService(game)
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["phase"] not in ("frame_confirmation", "judge_review") or not data["can_act"]:
        await reply(interaction, "This saved original exposure is read-only or complete.")
        return

    async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.decide,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["confirmed"][0] == "yes",
            values["account"],
        )
        return (
            "Your actual factual source decision is recorded; "
            "no current Frame/control/position changed."
        )

    form = NativeForm(
        interaction.user.id,
        "Original exposure: factual review",
        data["episode"],
        [
            Field(
                "confirmed",
                "Actual historical fact",
                (
                    ("yes", "Actual past link and chronology are confirmed"),
                    ("no", "Actual facts do not support this exposure"),
                ),
            ),
            Field("account", "Factual evidence and decision", paragraph=True),
        ],
        review,
    )
    await reply(interaction, form.text(), form)


async def open_virus_hub(interaction: discord.Interaction, game: Any) -> None:
    from girlframe.discord_adapter.m3_punishments import Picker
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_missions import MissionService

    viewer = viewer_from_interaction(interaction)
    roles = await asyncio.to_thread(ActorService(MissionService(game.store)).choices, viewer)
    from girlframe.engine.m3_enforcer_requisitions import VIRUS
    from girlframe.engine.m3_role_punishments import view
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_access import Access
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_enforcer_requisitions import owned

    def entries() -> dict[str, tuple[str, ActorRef]]:
        with game.store.engine.connect() as c:
            Access(game.store).authorize(c, viewer, "plays", director_response=True)
            canon = load_state(c, game.store.campaign_id)
            result = {}
            for entry in roles["actors"]:
                actor = ActorRef.model_validate(entry["ref"])
                actual = view(canon, actor, profiles(c, game.store.campaign_id))
                if owned(c, game, canon, actor, VIRUS) is not None:
                    result["virus:" + actor.token] = ("Compliance Virus — " + actual.label, actor)
                if actual.rules == "handler_girl":
                    result["exposure:" + actor.token] = (
                        "Record your actual past link exposure",
                        actor,
                    )
            return result

    available = await asyncio.to_thread(entries)
    if not available:
        await reply(
            interaction,
            "No actual owned Virus role or HandlerGirl factual-exposure role is available.",
        )
        return

    async def choose(current: discord.Interaction, token: str) -> None:
        actor = available[token][1]
        channel = current.channel_id or 0
        if token.startswith("exposure:"):
            await open_exposure_start(current, game, actor, channel)
        else:
            await open_virus(current, VirusService(game), actor, channel)

    picker = Picker(
        interaction.user.id,
        "Your actual source-owned Virus controls",
        tuple((key, value[0]) for key, value in available.items()),
        choose,
    )
    await picker.show(interaction)
