"""Actual Pair sources and privately owned Bonded choices."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_bonded import BondedService
from girlframe.services.onboarding import WorkflowError


def _answer(values: dict[str, Any]) -> ChoiceAnswer:
    content = {
        k: v
        for k, v in values.items()
        if k not in ("options", "identities", "tags") and isinstance(v, str)
    }
    return ChoiceAnswer(
        options=values.get("options", ()),
        denied=values.get("identities", values.get("tags", ())),
        text=json.dumps(content),
    )


def _choice_fields(data: dict[str, Any]) -> list[Field]:
    kind = data["kind"]
    fields = []
    if data["options"]:
        fields.append(
            Field(
                "options",
                "Your actual printed choice",
                tuple(tuple(x) for x in data["options"]),
                minimum=0 if kind == "bonded_mid" else 1,
                maximum=data["maximum"],
                required=kind != "bonded_mid",
            )
        )
    if kind == "bonded_mid" or kind == "bonded_low":
        if data["identities"]:
            fields.append(
                Field(
                    "identities",
                    "Unmark per request, up to all available marked Identities"
                    if kind == "bonded_mid"
                    else "Only if taking the continuing benefits: one marked Identity",
                    tuple((x["id"], x["label"]) for x in data["identities"]),
                    minimum=0,
                    maximum=min(4, len(data["identities"])),
                    required=False,
                )
            )
    if kind == "bonded_high" and data["tags"]:
        fields.append(
            Field(
                "tags",
                "Any of your actual Tags you give her; none is allowed",
                tuple((x["id"], x["label"]) for x in data["tags"]),
                minimum=0,
                maximum=len(data["tags"]),
                required=False,
            )
        )
    fields.append(Field("account", "Your actual words / performed outcome", paragraph=True))
    if kind == "bonded_side":
        fields.append(
            Field(
                "question", "If staying: ask when she comes for you", paragraph=True, required=False
            )
        )
        if data["tier"] == "high":
            fields.extend(
                [
                    Field("weapon_name", "If needed: actual found weapon name", required=False),
                    Field(
                        "weapon_description",
                        "If needed: actual found weapon description",
                        paragraph=True,
                        required=False,
                    ),
                ]
            )
    if kind == "bonded_reply":
        fields.append(
            Field(
                "content",
                "Your actual " + str(data.get("request") or "Tag") + " reply / performed change",
                paragraph=True,
                required=False,
            )
        )
    return fields


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data = decision.get("bonded") or decision["detail"]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            _answer(values),
        )
        return (
            "Your actual owned response is saved. "
            "Separate requests and actual Orders keep their controls."
        )

    form = NativeForm(
        interaction.user.id,
        "Bonded: your actual response",
        "Author only your own words and actions. Actual Pair replies belong to her. "
        "OOC safety remains available.",
        _choice_fields(data),
        submit,
    )
    await reply(interaction, form.text(), form)


async def _play(
    interaction: discord.Interaction,
    game: GameService,
    *,
    play: str,
    source: str,
    context: str,
    target: ActorRef | None = None,
    delegated_target: ActorRef | None = None,
    source_actor: ActorRef | None = None,
    channel: int | None = None,
    title: str = "Actual Bonded source Play",
) -> None:
    sheet = await asyncio.to_thread(game.sheet, viewer_from_interaction(interaction))
    identities = [x for x in sheet["identities"] if not x["marked"]]
    identities += [x for x in sheet.get("additional_identities", ()) if not x["marked"]]
    fields = [
        Field(
            "heat",
            "Actual Heat to spend",
            tuple((str(x), str(x)) for x in range(sheet["heat"] + 6)),
        )
    ]
    if identities:
        fields += [
            Field(
                "identity",
                "Optional actual unmarked Identity",
                tuple((x["id"], x["name"]) for x in identities),
                minimum=0,
                required=False,
            ),
            Field(
                "gain",
                "Heat from Identity (Paired exactly5)",
                tuple((str(x), str(x)) for x in (1, 2, 3, 5)),
            ),
            Field(
                "share",
                "Only Paired: Heat given to actual Pair",
                tuple((str(x), str(x)) for x in range(6)),
            ),
        ]
    battles: dict[str, Any] = {}
    combat_actor: dict[str, Any] = {}
    if play in ("all_out_assault", "go_for_the_core"):
        from girlframe.services.m3_battle import BattleService

        battle = await asyncio.to_thread(
            BattleService(game.store).preview,
            viewer_from_interaction(interaction),
            channel if channel is not None else int(interaction.channel_id or 0),
        )
        combat_actor = next(
            (
                x
                for x in battle["actors"]
                if source_actor is not None
                and x["ref"] == source_actor.model_dump(mode="json")
                and x["owned"]
            ),
            {},
        )
        battles = {
            x["id"]: x
            for x in battle["contexts"]
            if x["state"] == "confirmed"
            and x["owner"] == interaction.user.id
            and not x["source_action"]
            and not x.get("source_work")
            and x["declaration"]["play"] == play
            and x["declaration"]["actor"] == combat_actor.get("ref")
            and target is not None
            and x["declaration"]["target"] == target.model_dump(mode="json")
        }
        if not battles:
            await reply(
                interaction,
                "Use the Battle controls to declare your actual battle Play against this "
                "onlooker and obtain the facilitator's opening/reach confirmation, "
                "then return to this original witnessed-affection child. No roll was made.",
            )
            return
        fields.append(
            Field(
                "battle",
                "Your confirmed battle Play against this onlooker",
                tuple(
                    (key, value["declaration"]["account"][:100]) for key, value in battles.items()
                ),
            )
        )
    fields.append(Field("context", "Actual legal trigger / performed source", paragraph=True))

    async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
        combat = {}
        if play in ("all_out_assault", "go_for_the_core"):
            chosen = battles.get(values.get("battle", (None,))[0])
            if chosen is None:
                raise WorkflowError(
                    "Choose your confirmed battle Play against this original onlooker"
                )
            declared = chosen["declaration"]
            combat = dict(
                battle_context=chosen["id"],
                attacking_asset=declared["attacking_asset"],
                target_asset=declared["target_asset"],
                piloting=bool(combat_actor["piloting"]),
            )
        prepared = PlayInput(
            **combat,
            play=play,
            source_work=source,
            heat=int(values["heat"][0]),
            identity=values.get("identity", (None,))[0] if values.get("identity") else None,
            gain=int(values.get("gain", ("1",))[0]) if values.get("identity") else 0,
            pair_share=int(values.get("share", ("0",))[0]),
            target=(
                int(target.entity)
                if target and play not in ("engage", "all_out_assault", "go_for_the_core")
                else None
            ),
            target_actor=delegated_target,
            context=context if target is not None else values["context"],
            trigger_confirmed=True,
        )
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel if channel is not None else int(interaction.channel_id or 0),
            sheet["revision"],
            prepared,
        )
        return "Actual source Play prepared; resume its real roll/choices: " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        title,
        "Use real resources and your actual trigger. Preparing does not perform the Play.",
        fields,
        start,
    )
    await reply(interaction, form.text(), form)


async def open_child(interaction: discord.Interaction, game: GameService, child_id: str) -> None:
    service = BondedService(game)
    menu = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), None)
    for row in menu["history"]:
        data = await asyncio.to_thread(
            service.view, viewer_from_interaction(interaction), row["id"]
        )
        child = data.get("child")
        if child and child["id"] == child_id:
            if child["child"]:
                await reply(
                    interaction,
                    "Resume the actual child Play through its saved controls: " + child["child"],
                )
            else:
                await _play(
                    interaction,
                    game,
                    play=child["play"],
                    source=child_id,
                    context=child["account"],
                    target=ActorRef.model_validate(child["target"]),
                    delegated_target=(
                        ActorRef.model_validate(child["target"])
                        if child["play"] in ("engage", "all_out_assault", "go_for_the_core")
                        else None
                    ),
                    source_actor=ActorRef.model_validate(child["actor"]),
                    channel=data["channel"],
                )
            return
    await reply(interaction, "Open your original witnessed-affection source first.")


async def open_learned_bonded(
    interaction: discord.Interaction, service: BondedService, lesson: str
) -> None:
    data = await asyncio.to_thread(
        service.learned_menu,
        viewer_from_interaction(interaction),
        lesson,
        int(interaction.channel_id or 0),
    )
    pair = ActorRef.model_validate(data["pair"])
    nonpairs = {ActorRef.model_validate(x["ref"]).token: x for x in data["nonpairs"]}

    async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = (
            ActorRef.model_validate(nonpairs[values["nonpair"][0]]["ref"])
            if values.get("nonpair")
            else pair
        )
        if values.get("pair_rule") and target == pair:
            raise WorkflowError("The delegated Pair rule requires an actual non-Pair counterpart")
        result = await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            int(interaction.channel_id or 0),
            data["revision"],
            "sex",
            values["account"],
            target=target,
            route="delegated" if values.get("pair_rule") else "pair" if target == pair else "seven",
            delegated_rule=(
                "girl." + values["pair_rule"][0] + ".sex-play" if values.get("pair_rule") else None
            ),
            learned_source=lesson,
        )
        return "Invitation saved; the actual counterpart answers independently: " + str(
            result["id"]
        )

    form = NativeForm(
        interaction.user.id,
        "Learned Bonded source",
        "Your original Pair: " + data["pair_label"] + ". No new Pair or consent is granted.",
        [Field("account", "Your actual voluntary source", paragraph=True)]
        + (
            [
                Field(
                    "nonpair",
                    "Optional other person: default printed7, no roll (blank uses Pair)",
                    tuple((key, x["label"]) for key, x in nonpairs.items()),
                    minimum=0,
                    required=False,
                )
            ]
            if nonpairs
            else []
        )
        + (
            [
                Field(
                    "pair_rule",
                    "Optional alternative for non-Pair: actual Pair's rule",
                    tuple((x["id"].split(".")[1], x["label"]) for x in data["delegated_rules"]),
                    minimum=0,
                    required=False,
                )
            ]
            if data.get("delegated_rules") and nonpairs
            else []
        ),
        propose,
    )
    await reply(interaction, form.text(), form)


async def open_bonded(
    interaction: discord.Interaction, service: BondedService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, channel)
        options = [
            (
                x,
                {
                    "side": "Always By Her Side",
                    "intimacy": "Actual witnessed affection",
                    "sex": "Actual voluntary intimacy",
                }[x],
            )
            for x in data["available"]
        ]
        options += [(x["id"], x["label"]) for x in data["history"]]
        if not options:
            await reply(interaction, "No actual Bonded source or addressed private history here.")
            return

        async def pick(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            kind = values["source"][0]
            if kind not in ("side", "intimacy", "sex"):
                await open_bonded(current, service, kind)
                return None
            people = [x for x in data["people"] if kind != "intimacy" or x["ref"] != data["pair"]]
            fields = []
            if kind == "side":
                fields.append(
                    Field(
                        "apart",
                        "Actual fiction: I want to be with her and we are apart",
                        (("yes", "Yes, we are actually apart"),),
                    )
                )
            if kind != "side":
                fields.append(
                    Field(
                        "person",
                        "Actual onlooker" if kind == "intimacy" else "Actual intimate partner",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in people
                        ),
                    )
                )
            if kind == "sex":
                fields.append(
                    Field(
                        "route",
                        "Actual source route",
                        (
                            ("pair", "With my actual Pair"),
                            ("seven", "With someone else: actual unrolled7- result"),
                            ("delegated", "With someone else: use my Pair's actual Sex rule"),
                        ),
                    )
                )
            if kind == "sex" and len(data.get("delegated_rules", ())) > 1:
                fields.append(
                    Field(
                        "delegated_rule",
                        "Only borrowed route: actual current Pair Sex rule",
                        tuple((x["id"], x["label"]) for x in data["delegated_rules"]),
                        minimum=0,
                        required=False,
                    )
                )
            fields.append(
                Field("account", "Your actual voluntary source / factual affection", paragraph=True)
            )

            async def propose(response: discord.Interaction, answer: dict[str, Any]) -> str:
                person = next(
                    (
                        ActorRef.model_validate(x["ref"])
                        for x in people
                        if ActorRef.model_validate(x["ref"]).token in answer.get("person", ())
                    ),
                    None,
                )
                result = await asyncio.to_thread(
                    service.propose,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    data["revision"],
                    kind,
                    answer["account"],
                    target=person if kind == "sex" else None,
                    observer=person if kind == "intimacy" else None,
                    route=answer.get("route", ("pair",))[0],
                    apart=answer.get("apart") == ("yes",),
                    delegated_rule=answer.get("delegated_rule", (None,))[0]
                    if answer.get("delegated_rule")
                    else None,
                )
                return "Actual source saved; original people retain their choices: " + str(
                    result["id"]
                )

            form = NativeForm(
                current.user.id,
                "Actual Bonded source",
                "No consent, performance or private intention is inferred. "
                "Choose only actual original people.",
                fields,
                propose,
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Bonded: actual Pair and private history",
            "Your actual source controls.",
            [Field("source", "Source", tuple(options))],
            pick,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    summary = "Your actual " + data["kind"] + " source: " + data["phase"] + ". " + data["account"]
    if data.get("man_mark"):
        summary += (
            "\nActual Man partner-Tag mark: "
            + data["man_mark"]["label"]
            + "; source-only 11+ (no dice or Heat)."
        )
    resolution = data.get("man_resolution")
    paired = data.get("man_paired")
    if paired:
        summary += "\nActual marking Pair's choice: " + paired["label"] + " · " + paired["state"]
    if resolution:
        summary += "\nActual repeated Tag: " + resolution["label"] + " · " + resolution["state"]
        if resolution["decision"]:
            summary += " · original partner chose " + resolution["decision"]["decision"]
        if resolution["performance"]:
            summary += "\nActual performed rejection: " + resolution["performance"]["account"]
    if data.get("delegation"):
        summary += "\nActual delegated source: " + data["delegation"]["session"]
        if data["delegation"].get("action"):
            summary += " · actual Play " + data["delegation"]["action"]
    for detail in data["details"]:
        summary += "\n" + detail["kind"] + ": " + detail["account"]
    pause = data.get("pause")
    if pause:
        summary += "\nScene permission state: " + pause["state"]
        if pause.get("error"):
            summary += ". " + pause["error"]
    options = (
        [("retry_pause", "Retry actual scene permissions")] if pause and pause.get("retry") else []
    )
    if data.get("unrolled_gender"):
        options.append(("unrolled_gender", "Actual Animal Tag source / waiting state"))
    if resolution and resolution["can_resolve"]:
        options.append(("resolve_man_tag", "Your actual repeated Tag: embrace or reject"))
    if resolution and resolution["can_perform"]:
        options.append(("perform_man_rejection", "Your actual performed rejection action"))
    if paired and paired["can_choose"]:
        options.append(("choose_man_paired", "Your marking-Pair choice: make her Paired Identity"))
    for flag, label in (
        ("withdraw", "Withdraw your unbound learned invitation; keep the unused lesson"),
        ("confirm", "Your own voluntary participation response"),
        ("roll", "Actual source Play"),
        ("activate", "Record actual performed diceless source"),
        ("choose", "Your actual owned diceless outcome"),
        ("help", "Your genuine performed help"),
    ):
        if data.get("can_" + flag):
            options.append((flag, label))
    if data["child"]:
        options.append(("child", "Actual Play against the original onlooker"))
    if (
        data["route"] == "delegated"
        and data["phase"] in ("accepted", "bound", "complete")
        and viewer.user_id == int(data["actor"]["entity"])
    ):
        options.append(("delegated", "Use actual Pair-rule source without a copied person"))
    options += [("order:" + x["id"], "Issue your actual requested Order") for x in data["orders"]]
    if not options:
        await reply(
            interaction, summary + "\nResume actual pending rolled choices through Requests."
        )
        return

    async def operate(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "withdraw":
            await asyncio.to_thread(
                service.withdraw_learned,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Invitation withdrawn; the unused lesson is available for a fresh source."
        if operation == "retry_pause":
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry, service.game, viewer_from_interaction(current), str(current.id), identity
            )
            return "Actual scene permission restoration/retry queued. Reopen the source."
        if operation == "unrolled_gender":
            from girlframe.discord_adapter.p1_unrolled_sex import open_tasks

            await open_tasks(current, service.game, identity)
            return None
        if operation == "roll":
            await _play(
                current,
                service.game,
                play=rules.SIDE_PLAY if data["kind"] == "side" else rules.SEX_PLAY,
                source=identity,
                context=data["account"],
                channel=data["channel"],
            )
            return None
        if operation == "resolve_man_tag":
            assert resolution is not None
            choices = (
                [("embrace", "Embrace as a real replacement Identity")]
                if resolution["identities"]
                else []
            )
            if resolution["reject_allowed"]:
                choices.append(("reject", "Reject: owe an actual rejection action"))
            fields = [Field("decision", "Your actual repeated-Tag choice", tuple(choices))]
            if resolution["identities"]:
                fields.append(
                    Field(
                        "identity",
                        "If embracing: your actual legal Identity slot",
                        tuple((x["id"], x["label"]) for x in resolution["identities"]),
                        minimum=0,
                        required=False,
                    )
                )

            async def resolve(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.resolve_man_tag,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    ChoiceAnswer(
                        options=answer["decision"],
                        denied=answer.get("identity", ()),
                    ),
                )
                return "Your actual decision is saved. Reopen the source for any owed action."

            form = NativeForm(current.user.id, "Your actual repeated Tag", summary, fields, resolve)
            await reply(current, form.text(), form)
            return None
        if operation == "choose_man_paired":

            async def choose_paired(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.choose_man_paired,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["convert"][0] == "yes",
                )
                return "Your actual marking-Pair decision is saved. Reopen the source."

            form = NativeForm(
                current.user.id,
                "Your actual marking-Pair choice",
                summary,
                [
                    Field(
                        "convert",
                        "Make this actual Tag her new Paired Identity?",
                        (
                            ("yes", "Yes: turn this Tag into her actual Paired Identity"),
                            ("no", "No: keep her Paired Identity and marked Tag"),
                        ),
                    ),
                ],
                choose_paired,
            )
            await reply(current, form.text(), form)
            return None
        if operation == "perform_man_rejection":

            async def perform(response: discord.Interaction, answer: dict[str, Any]) -> str | None:
                if answer["trigger"][0] == "requires_play":
                    from girlframe.discord_adapter.m3_bonded_rejection import open_bonded_rejection
                    from girlframe.services.m3_bonded_rejection import BondedRejectionService

                    await open_bonded_rejection(
                        response,
                        BondedRejectionService(service.game),
                        identity=identity,
                        account=answer["account"],
                    )
                    return None
                await asyncio.to_thread(
                    service.perform_man_rejection,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["account"],
                    requires_play=answer["trigger"][0] == "requires_play",
                )
                return "Your actual performed rejection is saved. Reopen the original source."

            form = NativeForm(
                current.user.id,
                "Your actual rejection action",
                summary,
                [
                    Field(
                        "trigger",
                        "Does this action require a mandatory Play?",
                        (
                            ("no_roll", "Actually performed; no mandatory Play triggered"),
                            ("requires_play", "Choose the actual triggered Play"),
                        ),
                    ),
                    Field(
                        "account", "Your actual performed action rejecting this Tag", paragraph=True
                    ),
                ],
                perform,
            )
            await reply(current, form.text(), form)
            return None
        if operation == "child":
            await open_child(current, service.game, data["child"]["id"])
            return None
        if operation == "delegated":
            from girlframe.discord_adapter.m3_bonded_support import open_delegated

            await open_delegated(current, service.game, identity)
            return None
        fields = [Field("account", "Your actual words / performed factual account", paragraph=True)]
        if operation == "activate" and data.get("man_tags"):
            fields.insert(
                0,
                Field(
                    "man_tag",
                    "Optional Man mark: actual partner Tag for 11+ (otherwise take 7-)",
                    tuple((x["id"], x["label"]) for x in data["man_tags"]),
                    minimum=0,
                    required=False,
                ),
            )
        if operation == "confirm":
            fields.insert(
                0,
                Field(
                    "accept",
                    "Your actual voluntary choice",
                    (("yes", "Participate"), ("no", "Decline")),
                ),
            )
        if operation == "choose":
            if data["options"]:
                fields.insert(
                    0,
                    Field(
                        "options",
                        "Your actual printed outcome",
                        tuple(tuple(x) for x in data["options"]),
                    ),
                )
            if data["choice_kind"] == "bonded_high" and data["tags"]:
                fields.append(
                    Field(
                        "tags",
                        "Any of your actual Tags to give him; none is allowed",
                        tuple((x["id"], x["label"]) for x in data["tags"]),
                        minimum=0,
                        maximum=len(data["tags"]),
                        required=False,
                    )
                )
            if data["choice_kind"] == "bonded_low" and data["identities"]:
                fields.append(
                    Field(
                        "identities",
                        "Only if taking the continuing benefits: one marked Identity",
                        tuple((x["id"], x["label"]) for x in data["identities"]),
                        minimum=0,
                        required=False,
                    )
                )
            if data["kind"] == "intimacy":
                fields += [
                    Field("tag", "If Tag: actual label", required=False),
                    Field(
                        "play",
                        "If making Play: actual source",
                        (
                            ("flirt", "Flirt"),
                            ("brutalize", "Brutalize"),
                            ("snoop", "Snoop"),
                            ("engage", "Engage"),
                            ("put_someone_beneath_you", "Put Someone Beneath You"),
                            ("all_out_assault", "All Out Assault"),
                            ("go_for_the_core", "Go For the Core"),
                        ),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "context",
                        "If making Play: actual legal trigger",
                        paragraph=True,
                        required=False,
                    ),
                ]

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            who, key = viewer_from_interaction(response), str(response.id)
            if operation == "confirm":
                await asyncio.to_thread(
                    service.confirm,
                    who,
                    key,
                    identity,
                    data["revision"],
                    answer["accept"][0] == "yes",
                    answer["account"],
                )
            elif operation == "choose":
                if isinstance(answer.get("play"), tuple):
                    answer["play"] = answer["play"][0] if answer["play"] else ""
                await asyncio.to_thread(
                    service.choose, who, key, identity, data["revision"], _answer(answer)
                )
            elif operation.startswith("order:"):
                detail = next(x for x in data["orders"] if x["id"] == operation[6:])
                await asyncio.to_thread(
                    service.game.issue_order,
                    who,
                    key,
                    data["channel"],
                    int(detail["target"]["entity"]),
                    detail["account"],
                )
            elif operation == "activate":
                tags = answer.get("man_tag", ())
                await asyncio.to_thread(
                    service.activate,
                    who,
                    key,
                    identity,
                    data["revision"],
                    answer["account"],
                    man_tag=tags[0] if tags else None,
                )
            else:
                await asyncio.to_thread(
                    service.help,
                    who,
                    key,
                    identity,
                    data["revision"],
                    answer["account"],
                )
            return "Your actual source response is saved; reopen it through Requests."

        form = NativeForm(current.user.id, "Bonded: " + operation, summary, fields, submit)
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Your actual Bonded source",
        summary,
        [Field("operation", "Actual source control", tuple(options))],
        operate,
    )
    await reply(interaction, form.text(), form)
