"""Private source-owned Harpy Defeat selectors, actual replies and navigation reviews."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyTag
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


def cell(value: str) -> tuple[int, int] | None:
    if value.strip().lower() == "unknown":
        return None
    try:
        x, y = value.split(",")
        return int(x.strip()), int(y.strip())
    except (ValueError, TypeError):
        raise WorkflowError(
            "Use the actual map cell as x,y, or unknown when it is unknown."
        ) from None


def one(values: dict[str, Any], key: str, default: Any = None) -> Any:
    value = values.get(key)
    return value[0] if isinstance(value, tuple) and value else default


async def open_setup(
    interaction: discord.Interaction, service: HarpyDefeatService, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.setup_preview_actor, viewer_from_interaction(interaction), actor
    )
    choices = tuple((x["token"], x["label"]) for x in data["actors"])
    fields = [
        Field("linked", "Actual current link", (("yes", "Linked"), ("no", "Unlinked"))),
        Field("girl_cell", "Actual Girl cell: x,y or unknown"),
        Field("heat", "Actual current Heat"),
        Field(
            "identities",
            "Current Identities: one per line (blank if none)",
            paragraph=True,
            required=False,
        ),
        Field("shutdown", "Actual Frame state", (("no", "Active"), ("yes", "Shut down"))),
        Field("incapacitated", "Actual body state", (("no", "Active"), ("yes", "Incapacitated"))),
        Field(
            "custody",
            "Actual custody",
            (
                ("free", "Free"),
                ("captured", "Captured"),
                ("transported", "Transported"),
                ("core", "Held in a Core"),
            ),
        ),
        Field("custodian", "Actual custodian if held", choices, minimum=0, required=False),
        Field("account", "Actual factual resources and physical situation", paragraph=True),
    ]
    for index, tag in enumerate(data["tags"]):
        fields.append(Field("setter_" + str(index), "Original setter of " + tag["label"], choices))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        refs = {x["token"]: ActorRef.model_validate(x["ref"]) for x in data["actors"]}
        tags = tuple(
            HarpyTag(
                id=tag["id"],
                label=tag["label"],
                giver_ref=refs[one(values, "setter_" + str(index))],
                giver=int(refs[one(values, "setter_" + str(index))].entity)
                if refs[one(values, "setter_" + str(index))].kind in ("pilot", "handler")
                else next(
                    x["controller"]
                    for x in data["actors"]
                    if x["token"] == one(values, "setter_" + str(index))
                ),
            )
            for index, tag in enumerate(data["tags"])
        )
        facts = NativeHarpyFacts(
            actor=actor,
            linked=one(values, "linked") == "yes",
            girl_cell=cell(values["girl_cell"]),
            frame_cell=tuple(data["frame_cell"]),
            heat=int(values["heat"]),
            frame_shutdown=one(values, "shutdown") == "yes",
            body_incapacitated=one(values, "incapacitated") == "yes",
            custody=one(values, "custody"),
            custodian=refs.get(one(values, "custodian")),
            identities=tuple(
                HarpyIdentity(id=str(uuid4()), name=name.strip())
                for name in values.get("identities", "").splitlines()
                if name.strip()
            ),
            tags=tags,
            account=values["account"],
            facts_confirmed=True,
        )
        await asyncio.to_thread(
            service.propose_runtime,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            facts,
        )
        return "Your actual Harpy facts await the real GM's review in their inbox."

    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Actual native Harpy setup",
        "Record existing resources and facts. This creates no PC origin, Assets or Heat bonus. "
        "The GM must review the exact proposal before this Harpy can roll.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_defeat(
    interaction: discord.Interaction, service: HarpyDefeatService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    tasks = await asyncio.to_thread(service.tasks, viewer)
    data = next((x for x in tasks if x["kind"] == "harpy_defeat" and x["id"] == identity), None)
    if data is None:
        raise WorkflowError("Open your actual pending Harpy Defeat source.")
    if data.get("action"):
        action = await asyncio.to_thread(service.inspect, viewer, data["action"])
        owned = next((x for x in action["pending"] if x["owner"] == viewer.user_id), None)
        if owned:
            await open_choice(interaction, service, owned["id"])
        else:
            await reply(
                interaction,
                "Your actual Harpy Defeat is "
                + action["state"]
                + ". Another original participant may have a pending response.",
            )
        return
    # Actual World Harpies need their own reviewed factual runtime, never a proxy PC.
    try:
        preview = await asyncio.to_thread(service.setup_preview, viewer, identity)
    except WorkflowError:
        preview = None
    if preview is not None:
        await open_setup(interaction, service, ActorRef.model_validate(preview["actor"]))
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.begin,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            channel=None,
        )
        return "Actual Harpy Defeat confirmed. The source chat lock is acquired before one roll."

    form = NativeForm(
        viewer.user_id,
        "Actual Harpy Defeat",
        "This mandatory source rolls 2d6+2, "
        "or +4 with an actual Intense Bond to a Girl in this scene. It spends no Heat.",
        [
            Field(
                "confirm",
                "Confirm the actual source",
                (("yes", "Begin this original Harpy Defeat"),),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_choice(
    interaction: discord.Interaction, service: HarpyDefeatService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.decision, viewer, identity)
    if data["state"] != "pending":
        await reply(interaction, "This original choice already has an actual saved response.")
        return
    kind = data["kind"]
    if kind == "manual_adjudication":
        from girlframe.discord_adapter.m3_adjudication import open_adjudication
        from girlframe.services.m3_adjudication import AdjudicationService

        await open_adjudication(interaction, AdjudicationService(service.store), identity)
        return
    if kind == "harpy_defeat_select":
        options = {
            "mid": (
                ("message", "Send final comms; deepen Bond"),
                ("rift", "Open a Voidspace Rift; escape"),
            ),
            "high": (
                ("kidnap", "Kidnap an actually defeated Girl; escape"),
                ("foundation", "Shut down and let the Foundation take you"),
                ("plead", "Ask a Girl to come; escape either way"),
            ),
            "low": (
                ("death", "Die; inflict a Tag on your actual killer"),
                ("shutdown", "Frame shuts down: surrender or sever link"),
                ("rescue", "Another actual scene Harpy rescues you"),
            ),
        }[data["tier"]]

        async def select(current: discord.Interaction, choice: str) -> None:
            if choice == "physical":
                from girlframe.discord_adapter.m3_harpy_physical import open_physical
                from girlframe.services.m3_harpy_physical import HarpyPhysicalService

                await open_physical(
                    current,
                    HarpyPhysicalService(service.store),
                    ActorRef.model_validate(data["actor"]),
                )
                return
            await outcome_form(current, service, data, choice)

        if data.get("physical_controls"):
            options += (("physical", "Actual Frame consent and physical recovery controls"),)

        await reply(
            interaction,
            "Choose one actual printed Harpy Defeat result.",
            Picker(viewer.user_id, "Choose your result", options, select),
        )
        return
    fields: list[Field] = []
    if kind == "tag_window":
        fields.append(
            Field(
                "mode",
                "Your actual Tag response",
                (("pass", "Pass"), ("tag", "Propose an observed Tag")),
            )
        )
        fields.append(
            Field("account", "Actual Tag proposal explanation", paragraph=True, required=False)
        )
        fields.extend(
            (
                Field(
                    "tag",
                    "Actual observed unused Tag",
                    tuple((x["id"], x["label"]) for x in data["tags"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "marker",
                    "Your actual role",
                    tuple((x["token"], x["label"]) for x in data["markers"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "direction",
                    "Direction if proposing",
                    (("1", "Help"), ("-1", "Hinder")),
                    minimum=0,
                    required=False,
                ),
            )
        )
    elif kind == "harpy_tag_resolution":
        options = (
            (("embrace", "Embrace"), ("reject", "Defer actual Rejection"))
            if data["can_reject"]
            else (("embrace", "Embrace"),)
        )
        fields.append(Field("mode", "Resolve your repeated Tag", options))
        fields.append(
            Field(
                "replace",
                "Ordinary Identity to replace if embracing",
                tuple((x["id"], x["name"]) for x in data["identities"]),
                minimum=0,
                maximum=max(1, data["replace_count"]),
                required=False,
            )
        )
    elif kind == "harpy_girl_plea":
        fields.extend(
            (
                Field(
                    "mode",
                    "Your actual Girl's answer",
                    (
                        ("come", "Come with the Harpy"),
                        ("refuse", "Refuse; raise Status and give her a Tag"),
                    ),
                ),
                Field("tag", "Tag you give her if refusing", required=False),
                Field("account", "Your actual response", paragraph=True),
            )
        )
    elif kind in ("harpy_killer_fact", "harpy_capture_fact"):
        if kind == "harpy_killer_fact" and data.get("needs_killer"):
            fields.append(
                Field(
                    "killer",
                    "Actual original killer",
                    tuple((x["token"], x["label"]) for x in data["actors"]),
                )
            )
        if kind == "harpy_capture_fact":
            fields.append(
                Field(
                    "captor",
                    "Actual present Foundation captor",
                    tuple((x["token"], x["label"]) for x in data["actors"]),
                )
            )
        fields.extend(
            (
                Field("account", "Actual killer or custody facts", paragraph=True),
                Field(
                    "confirm", "Confirm actual source facts", (("yes", "These are actual facts"),)
                ),
            )
        )
    elif kind == "harpy_tag_select":
        fields.append(
            Field(
                "candidate",
                "Actual human Tag proposer",
                tuple(
                    (str(x), "Original proposer " + str(x)) for x in data.get("tag_candidates", ())
                ),
            )
        )
        fields.append(Field("account", "Actual table discussion", paragraph=True))
    elif kind == "harpy_tag_agreement":
        fields.extend(
            (
                Field("agree", "Your actual agreement", (("yes", "Agree"), ("no", "Disagree"))),
                Field("account", "Your actual discussion response", paragraph=True),
            )
        )
    else:
        raise WorkflowError("Resume this actual source-owned Harpy response from its inbox.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "tag_window":
            mode = one(values, "mode")
            answer = ChoiceAnswer(
                options=(mode,),
                denied=(one(values, "tag"),) if mode == "tag" else (),
                number=int(one(values, "direction")) if mode == "tag" else None,
                text=values.get("account", "") if mode == "tag" else "",
                fields={"marker": one(values, "marker")} if mode == "tag" else {},
            )
        elif kind == "harpy_tag_resolution":
            answer = ChoiceAnswer(options=(one(values, "mode"),), denied=values.get("replace", ()))
        elif kind == "harpy_girl_plea":
            answer = ChoiceAnswer(
                options=(one(values, "mode"),),
                text=values["account"],
                fields={"tag": values.get("tag", "")},
            )
        elif kind in ("harpy_killer_fact", "harpy_capture_fact"):
            answer = ChoiceAnswer(
                text=values["account"], flag=True, fields={"captor": one(values, "captor", "")}
            )
        elif kind == "harpy_tag_select":
            answer = ChoiceAnswer(options=(one(values, "candidate"),), text=values["account"])
        else:
            answer = ChoiceAnswer(flag=one(values, "agree") == "yes", text=values["account"])
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return (
            "Your actual source-owned response is saved. Remaining decisions stay "
            "in their owners' inboxes."
        )

    form = NativeForm(
        viewer.user_id,
        "Actual Harpy response",
        "Only your own response is recorded. "
        "Physical custody and Frame consent remain actual source-owned gates.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def outcome_form(
    interaction: discord.Interaction, service: HarpyDefeatService, data: dict[str, Any], choice: str
) -> None:
    fields = [Field("account", "Your actual result or comms", paragraph=True)]
    if choice in ("message", "plead", "kidnap"):
        fields.append(
            Field(
                "girl",
                "Actual original Girl in scene",
                tuple((x["token"], x["label"]) for x in data["girls"]),
            )
        )
    elif choice in ("rescue", "death"):
        actors = data["actors"]
        if choice == "rescue":
            actors = [x for x in actors if str(x.get("girl", "")).lower() == "harpy"]
        if choice == "rescue" or not data.get("has_source_killer"):
            fields.append(
                Field(
                    "rescuer" if choice == "rescue" else "killer",
                    "Actual scene Harpy" if choice == "rescue" else "Actual killer, if known",
                    tuple((x["token"], x["label"]) for x in actors),
                    minimum=1 if choice == "rescue" else 0,
                    required=choice == "rescue",
                )
            )
        if choice == "death":
            fields.append(Field("tag", "Tag inflicted on your actual killer"))
    elif choice == "shutdown":
        fields.append(
            Field(
                "cut",
                "After Frame shutdown",
                (("no", "Let them take you"), ("yes", "Sever link; fight until actually Helpless")),
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        answer = ChoiceAnswer(
            options=(choice,),
            text=values["account"],
            fields={
                k: one(values, k) if isinstance(values[k], tuple) else values[k]
                for k in ("girl", "rescuer", "killer", "tag")
                if k in values
            },
            flag=one(values, "cut") == "yes" if choice == "shutdown" else None,
        )
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            answer,
        )
        return "Your actual result is saved. Any real Girl reply or factual review remains pending."

    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Harpy result: " + choice,
        "Escape preserves unknown offstage position and existing resources. "
        "Kidnapping needs actual "
        "physical access; extraction always respects the actual Frame consent gate.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def route_form(
    interaction: discord.Interaction,
    service: HarpyDefeatService,
    data: dict[str, Any],
    actor: ActorRef,
    *,
    rift: str | None = None,
    escape_effect: str | None = None,
    return_of: str | None = None,
) -> None:
    fields = [
        Field("account", "Actual journey or return facts", paragraph=True),
        Field("navigation", "Actual means of navigating Voidspace", paragraph=True),
    ]
    if rift is None or return_of is not None:
        fields.append(Field("destination", "Actual return cell: x,y"))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.propose_route,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            actor,
            rift=rift,
            escape_effect=escape_effect,
            return_of=return_of,
            destination=cell(values["destination"]) if "destination" in values else None,
            account=values["account"],
            navigation=values["navigation"],
        )
        return (
            "Actual navigation proposal saved for its source adjudicator's review; "
            "no movement is assumed."
        )

    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Actual Voidspace navigation",
        "A Rift does not grant navigation. Describe the real means and route for the GM to review. "
        "Unknown offstage position remains unknown until an actual return is reviewed.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_task(
    interaction: discord.Interaction, service: HarpyDefeatService, kind: str, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.task, viewer_from_interaction(interaction), kind, identity
    )
    if kind == "harpy_defeat":
        await open_defeat(interaction, service, identity)
        return
    if kind == "harpy_message":
        await reply(interaction, "Actual final comms from the original Harpy:\n" + data["account"])
        return
    if kind == "harpy_escape":
        await route_form(
            interaction,
            service,
            data,
            ActorRef.model_validate(data["actor"]),
            escape_effect=data["effect"],
        )
        return
    if kind == "harpy_return":
        route = data["route"]
        await route_form(
            interaction,
            service,
            data,
            ActorRef.model_validate(route["actor"]),
            rift=route["rift"],
            escape_effect=route["escape_effect"],
            return_of=identity,
        )
        return
    if kind == "harpy_rift":

        async def select(current: discord.Interaction, selection: str) -> None:
            if selection == "close":
                await asyncio.to_thread(
                    service.close_rift,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                )
                await reply(
                    current,
                    "The actual owner closed this Rift. Existing offstage bodies "
                    "remain where they actually are.",
                )
            else:
                actor = next(x for x in data["actors"] if x["token"] == selection)
                await route_form(
                    current, service, data, ActorRef.model_validate(actor["ref"]), rift=identity
                )

        options = tuple((x["token"], "Propose following: " + x["label"]) for x in data["actors"])
        if data["can_close"]:
            options += (("close", "Owner: close this actual Rift"),)
        await reply(
            interaction,
            data["rift"]["description"],
            Picker(
                viewer_from_interaction(interaction).user_id,
                "Actual Rift controls",
                options,
                select,
            ),
        )
        return
    if kind == "harpy_fight":
        if not data["can_act"]:
            await reply(
                interaction,
                "This original Harpy must continue fighting until an actual consequence "
                "makes her Helpless. No acknowledgement can replace that condition.",
            )
            return

        async def finish(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.finish_fight,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return (
                "The original source's actual Helpless condition completes the "
                "continuing-fight requirement."
            )

        form = NativeForm(
            viewer_from_interaction(interaction).user_id,
            "Actual fight consequence",
            "The canonical original body is now actually Helpless.",
            [
                Field(
                    "confirm",
                    "Record actual condition",
                    (("yes", "Use the actual source-proved Helpless condition"),),
                )
            ],
            finish,
        )
        await reply(interaction, form.text(), form)
        return
    if not data["can_act"]:
        await reply(
            interaction, "This exact owned factual proposal is awaiting its actual adjudicator."
        )
        return
    if kind == "harpy_setup":
        setup = data["setup"]
        info = setup["facts"]
        summary = (
            "Review actual native Harpy facts: Heat "
            + str(info["heat"])
            + "; linked "
            + str(info["linked"])
            + "; Girl cell "
            + str(info["girl_cell"])
            + "; Frame cell "
            + str(info["frame_cell"])
            + ".\n"
            + info["account"]
            + "\nIdentities: "
            + ", ".join(x["name"] for x in info["identities"])
            + "\nTags: "
            + ", ".join(x["label"] for x in info["tags"])
        )
    elif kind == "harpy_route":
        value = data["route"]
        summary = (
            "Actual owned navigation proposal:\n"
            + value["account"]
            + "\nNavigation: "
            + value["navigation"]
            + "\nDestination: "
            + str(value["destination"])
        )
    else:
        raise WorkflowError("Open the actual source-owned Harpy task.")

    async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
        allow = one(values, "allow") == "yes"
        if kind == "harpy_setup":
            await asyncio.to_thread(
                service.review_setup,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                allow,
                values["account"],
            )
        else:
            await asyncio.to_thread(
                service.review_route,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                allow=allow,
                account=values["account"],
            )
        return "Your actual source-owned factual review is saved."

    form = NativeForm(
        viewer_from_interaction(interaction).user_id,
        "Actual factual review",
        summary,
        [
            Field(
                "allow",
                "Your actual source review",
                (("yes", "Approve these actual facts"), ("no", "Reject this proposal")),
            ),
            Field("account", "Actual factual review and evidence", paragraph=True),
        ],
        review,
    )
    await reply(interaction, form.text(), form)
