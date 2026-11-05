"""Owned native Leviathan influence declarations and actual result choices."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_leviathan_obsession_state import GrantedIdentity
from girlframe.engine.m3_leviathan_roll_state import Declaration, FactualIdentities
from girlframe.services.m3_leviathan_obsession import ObsessionService
from girlframe.services.onboarding import WorkflowError


async def open_influence(interaction: discord.Interaction, service: ObsessionService) -> None:
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    sources = [x for x in data["actors"] if x["leviathan"] and x["owned"]]
    if not sources:
        await reply(
            interaction, "Join your Leviathan to this scene before declaring its influence."
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        source = next(
            x for x in sources if ActorRef.model_validate(x["ref"]).token == values["source"][0]
        )
        subject = next(
            x
            for x in data["actors"]
            if ActorRef.model_validate(x["ref"]).token == values["subject"][0]
        )
        if source["ref"] == subject["ref"]:
            raise WorkflowError("Choose another actual person as the subject")
        modes = (("give", "Give an obsessed Tag"),) + tuple(
            (x["id"], "Mark obsessed: " + x["label"]) for x in subject["trigger_tags"]
        )

        async def submit(next_interaction: discord.Interaction, details: dict[str, Any]) -> str:
            selected = details["mode"][0]
            result = await asyncio.to_thread(
                service.begin,
                viewer_from_interaction(next_interaction),
                str(next_interaction.id),
                int(next_interaction.channel_id or 0),
                data["revision"],
                Declaration(
                    mode="give_tag" if selected == "give" else "succumb",
                    source=ActorRef.model_validate(source["ref"]),
                    subject=ActorRef.model_validate(subject["ref"]),
                    source_sha256=source["source_sha256"],
                    subject_sha256=subject["source_sha256"],
                    tag=None if selected == "give" else selected,
                    account=details["account"],
                    reach_confirmed=True,
                ),
            )
            return "Influence saved. Owned responses appear in /character requests. Action: " + str(
                result["action_id"]
            )

        form = NativeForm(
            current.user.id,
            "Leviathan influence",
            "Describe the actual influence and reach. The affected person's resources are used.",
            [
                Field("mode", "Influence", modes),
                Field("account", "Describe the actual influence", paragraph=True),
            ],
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        interaction.user.id,
        "Leviathan influence",
        "Choose the original source and subject present in this scene.",
        [
            Field(
                "source",
                "Your Leviathan",
                tuple((ActorRef.model_validate(x["ref"]).token, x["name"]) for x in sources),
            ),
            Field(
                "subject",
                "Actual subject",
                tuple((ActorRef.model_validate(x["ref"]).token, x["name"]) for x in data["actors"]),
            ),
        ],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_choice(
    interaction: discord.Interaction, service: ObsessionService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.game.decision, viewer_from_interaction(interaction), identity
    )
    kind, detail = data["kind"], data["detail"]
    fields: list[Field] = []
    description = "Your original owned response is saved with this Play."
    if kind == "tag_window":
        fields = [
            Field(
                "tag",
                "Tag response",
                (("pass", "Pass"),) + tuple((x["id"], x["label"]) for x in detail["tags"]),
            )
        ]
        if detail["tags"]:
            fields += [
                Field("direction", "Modifier", (("1", "Help"), ("-1", "Hinder"))),
                Field(
                    "marker", "Actual role", tuple((x["id"], x["label"]) for x in detail["markers"])
                ),
                Field("account", "Why this Tag applies", paragraph=True, required=False),
            ]
        if detail.get("can_status"):
            fields += [Field("status", "Mark Status?", (("0", "No"), ("1", "+1"), ("-1", "-1")))]
    elif kind in ("leviathan_trigger_tag", "leviathan_tag_resolution"):
        options = detail["options"]
        choices: tuple[tuple[str, str], ...] = ()
        if options.get("reject"):
            choices += (("reject", "Owe an actual action rejecting this Tag"),)
        if options.get("embrace"):
            choices += (("embrace", "Embrace this Tag as an Identity"),)
        if options.get("needs_factual_identities"):
            choices += (("review_facts", "Review my existing Identities"),)
        fields = [Field("response", "Repeated Tag", choices)]
        if detail["replacements"]:
            fields += [
                Field(
                    "replace",
                    "If needed, replace Identity",
                    (("none", "No replacement"),)
                    + tuple((x["id"], x["label"]) for x in detail["replacements"]),
                )
            ]
    elif kind == "leviathan_identity_result":
        fields = [
            Field(
                "result",
                "Your Identity result",
                tuple((x["id"], x["label"]) for x in detail["options"]),
            )
        ]
    elif kind == "leviathan_facts":
        facts = detail["facts"]
        if facts["needs_import"]:
            description = (
                "Record existing resources, not a new build. List one Identity per line. "
                "The adjudicator reviews these facts."
            )
            fields = [
                Field(
                    "ordinary",
                    "Existing ordinary Identities (one per line)",
                    paragraph=True,
                    required=False,
                ),
                Field(
                    "protected", "Protected extras (one per line)", paragraph=True, required=False
                ),
                Field("paired", "Paired Identity (if any)", required=False),
                Field(
                    "marked", "Marked Identity names (one per line)", paragraph=True, required=False
                ),
            ]
        else:
            eligible = [x for x in facts["existing"] if not x["protected"] and not x["paired"]]
            fields = (
                [
                    Field(
                        "ordinary_ids",
                        "Actual ordinary slots",
                        tuple((x["id"], x["name"]) for x in eligible),
                        minimum=0,
                        maximum=min(4, len(eligible)),
                    )
                ]
                if eligible
                else []
            )
        if facts["mentor_options"]:
            fields += [
                Field(
                    "mentor",
                    "Existing Mentor, if applicable",
                    (("none", "No Mentor"),)
                    + tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in facts["mentor_options"]
                    ),
                )
            ]
        fields += [Field("account", "Source of these existing facts", paragraph=True)]
    elif kind == "leviathan_facts_review":
        description = "Review the owner's existing Identity facts: " + ", ".join(
            x["name"] for x in detail["facts"].get("identities", [])
        )
        fields = [
            Field(
                "approve",
                "Factual review",
                (("yes", "These existing facts are correct"), ("no", "Return for correction")),
            ),
            Field("account", "Review account", paragraph=True),
        ]
    elif kind in ("leviathan_tag_selection", "leviathan_tag_agreement"):
        description = "Discuss the actual saved Tag proposals with the table."
        fields = (
            [
                Field(
                    "proposal",
                    "Proposal",
                    tuple((x["id"], x["label"]) for x in detail["proposals"]),
                )
            ]
            if kind.endswith("selection")
            else [Field("approve", "Table agreement", (("yes", "Agree"), ("no", "Disagree")))]
        )
        fields += [Field("account", "Your account", paragraph=True)]
    elif kind == "leviathan_pair_tag":
        fields = [
            Field(
                "rename",
                "Rename your protected Paired Identity?",
                (("no", "Keep current Identity"), ("yes", "Rename it")),
            ),
        ]
    elif kind == "leviathan_low_play":
        fields = [Field("account", "How do you play it now?", paragraph=True)]
    elif kind.startswith("leviathan_arrival_"):
        requirement = detail["arrival"]
        if requirement["blocker"]:
            await reply(
                interaction,
                "Arrival needs the existing physical prerequisite: " + requirement["blocker"],
            )
            return
        description = (
            "Confirm an actually completed journey along the influence trail. "
            "This does not grant transport, extraction or Frame control."
        )
        fields = [
            Field("approve", "Actual arrival", (("yes", "I confirm the actual arrival"),)),
            Field("account", "Describe what actually happened", paragraph=True),
        ]
    elif kind == "leviathan_reach":
        fields = [
            Field(
                "approve",
                "Actual influence reaches the subject?",
                (("yes", "Confirm"), ("no", "Reject")),
            ),
            Field("account", "Factual review", paragraph=True),
        ]
    else:
        raise WorkflowError("This Leviathan response is not supported by the current controls")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        answer = ChoiceAnswer()
        if kind == "tag_window":
            selected = values["tag"][0]
            answer = ChoiceAnswer(
                options=(selected,),
                number=int(values["direction"][0]) if selected != "pass" else None,
                text=values.get("account", "") if selected != "pass" else "",
                fields=({"marker": values["marker"][0]} if selected != "pass" else {})
                | ({"status": values["status"][0]} if "status" in values else {}),
            )
        elif kind in ("leviathan_trigger_tag", "leviathan_tag_resolution"):
            replacement = values.get("replace", ("none",))[0]
            answer = ChoiceAnswer(
                options=values["response"],
                denied=(replacement,)
                if replacement != "none" and values["response"] == ("embrace",)
                else (),
            )
        elif kind == "leviathan_identity_result":
            answer = ChoiceAnswer(options=values["result"])
        elif kind == "leviathan_facts":
            facts = detail["facts"]
            imported: list[GrantedIdentity] = []
            ordinary: tuple[str, ...] = values.get("ordinary_ids", ())
            if facts["needs_import"]:
                marked = {x.strip() for x in values.get("marked", "").splitlines() if x.strip()}
                for key in ("ordinary", "protected", "paired"):
                    for name in values.get(key, "").splitlines():
                        if name.strip():
                            imported.append(
                                GrantedIdentity(
                                    id=str(uuid4()),
                                    name=name.strip(),
                                    marked=name.strip() in marked,
                                    protected=key == "protected",
                                    paired=key == "paired",
                                )
                            )
                if len({x.name for x in imported}) != len(imported) or not marked <= {
                    x.name for x in imported
                }:
                    raise WorkflowError(
                        "Use distinct existing Identity names and mark only names you listed"
                    )
                ordinary = tuple(x.id for x in imported if not x.protected and not x.paired)
            mentor = next(
                (
                    ActorRef.model_validate(x["ref"])
                    for x in facts["mentor_options"]
                    if ActorRef.model_validate(x["ref"]).token == values.get("mentor", ("none",))[0]
                ),
                None,
            )
            answer = ChoiceAnswer(
                fields={
                    "facts": FactualIdentities(
                        ordinary=ordinary,
                        identities=tuple(imported),
                        mentor=mentor,
                        account=values["account"],
                    ).model_dump_json()
                }
            )
        elif kind == "leviathan_tag_selection":
            answer = ChoiceAnswer(options=values["proposal"], text=values["account"])
        elif kind == "leviathan_pair_tag":
            answer = ChoiceAnswer(options=values["rename"])
        elif kind == "leviathan_low_play":
            answer = ChoiceAnswer(text=values["account"])
        else:
            answer = ChoiceAnswer(flag=values["approve"][0] == "yes", text=values["account"])
        await asyncio.to_thread(
            service.game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your response is saved. Continue any remaining choices in /character requests."

    form = NativeForm(interaction.user.id, "Leviathan: your response", description, fields, submit)
    await reply(interaction, form.text(), form)
