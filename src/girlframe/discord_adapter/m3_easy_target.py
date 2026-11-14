"""Private original-person Easy Target choices and genuine performance controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.m3_easy_target import EasyTargetService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any] | str
) -> None:
    if isinstance(decision, str):
        decision = await asyncio.to_thread(
            game.decision, viewer_from_interaction(interaction), decision
        )
    if decision["kind"] == "battle_target_damage" and decision.get("body", {}).get(
        "easy_target_npc_hurt"
    ):
        from girlframe.discord_adapter.m3_battle import open_battle

        await open_battle(interaction, game, decision["id"])
        return
    detail = decision.get("detail") or decision["easy_target"]
    kind = detail["kind"]
    if kind == "easy_target_child":
        work = detail["work"]
        if work["urge"] == "cohort" and not any(
            detail.get(x) for x in ("protection_cohort", "use_cohort", "hurt_cohort")
        ):
            await reply(
                interaction,
                "Actually assist the selected primary's child with your own "
                "positive Tag modifier. This obligation closes only when it is applied.",
            )
            return
        if work["urge"] == "hurt" and not detail.get("npc_hurt"):
            from girlframe.discord_adapter.m3_battle import open_declaration
            from girlframe.services.m3_battle import BattleService

            source = EasyTargetService(game).view(viewer_from_interaction(interaction), work["id"])[
                "source"
            ]
            parent = decision | dict(
                body=dict(actor=work["actor"], attacker=source["actor"]),
                parent=work["session"],
                channel=detail["channel"],
            )
            await open_declaration(interaction, BattleService(game.store), parent=parent)
            return
        if not any(
            detail.get(x)
            for x in (
                "npc_hurt",
                "npc_protect",
                "npc_use",
                "pilot_use",
                "handler_use",
                "handler_protect",
                "pilot_protect",
                "protection_cohort",
                "use_cohort",
                "hurt_cohort",
            )
        ):
            from girlframe.discord_adapter.m2_ui import open_play

            await open_play(interaction, game, parent=decision)
            return
    fields: list[Field] = []
    if kind == "easy_target_select":
        fields.append(
            Field(
                "select",
                "Actual other scene person",
                tuple((x["id"], x["label"]) for x in detail["roles"]),
            )
        )
    elif kind == "easy_target_react":
        from girlframe.engine.m2 import PLAY_IDS

        fields.extend(
            [
                Field(
                    "urge",
                    "Your actual reaction",
                    tuple((x, x.replace("_", " ")) for x in detail["urges"]),
                ),
                Field(
                    "primary",
                    "If cohort: actual other primary",
                    tuple((x["id"], x["label"]) for x in detail["primaries"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "play",
                    "Triggered Play (blank for ordinary use/protection)",
                    tuple((x, x.replace("_", " ")) for x in PLAY_IDS + ("all_out_assault",)),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "context",
                    "Actual task, protective action or performance trigger",
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    elif kind in (
        "easy_target_validate",
        "easy_target_bond",
        "easy_target_judge",
        "easy_target_failure",
    ):
        labels = {
            "easy_target_validate": "Validate the actual supported source and trigger",
            "easy_target_bond": "Deepen your actual Bond after completed use",
            "easy_target_judge": "Was the Newgirl's actual completed work done well?",
            "easy_target_failure": "Give the original protector a Tag after actual failure",
        }
        fields.append(
            Field(
                "yes",
                labels[kind],
                (("yes", "Yes"),)
                if kind == "easy_target_validate"
                else (("yes", "Yes"), ("no", "No")),
            )
        )
    elif kind == "easy_target_contempt":
        fields.append(
            Field(
                "performance",
                "Your actual performed contempt",
                (
                    ("look", "Give a disgusted look"),
                    ("spit", "Spit"),
                    ("leave", "Leave as this actual person"),
                ),
            )
        )
    if kind == "easy_target_child" and any(
        detail.get(x) for x in ("use_cohort", "hurt_cohort", "protection_cohort")
    ):
        fields.append(
            Field(
                "outcome",
                "Your own actual participation",
                (("missed", "Acknowledge missed participation"),)
                if any(
                    detail.get(x)
                    for x in ("use_cohort_missed", "hurt_cohort_missed", "protection_cohort_missed")
                )
                else (
                    ("participate", "Record actual participation"),
                    ("decline", "Decline participation"),
                ),
            )
        )
    fields.append(
        Field(
            "account",
            "Actual Tag label"
            if kind in ("easy_target_tag", "easy_target_failure")
            else "Your actual source-specific account",
            paragraph=True,
        )
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        assert isinstance(decision, dict)
        options = tuple(values.get("select", values.get("urge", values.get("performance", ()))))
        if values.get("outcome"):
            options = tuple(values["outcome"])
        specific = {x: values[x][0] for x in ("primary", "play") if values.get(x)}
        if values.get("context"):
            specific["context"] = values["context"]
        if (
            kind == "easy_target_react"
            and detail.get("npc_reactor")
            and options in (("hurt",), ("protect",))
        ):
            specific.pop("play", None)
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=options,
                text=values["account"],
                fields=specific,
                flag=values["yes"][0] == "yes" if values.get("yes") else None,
            ),
        )
        return "Your original person's actual Easy Target choice is saved."

    async def access(current: discord.Interaction) -> None:
        assert isinstance(decision, dict)
        await asyncio.to_thread(game.decision, viewer_from_interaction(current), decision["id"])

    form = MemoryForm(
        interaction.user.id,
        "Easy Target",
        (
            "The NPC's bodily action was already performed before you participated. "
            "Acknowledge the missed opportunity without exemption. The actual injury and "
            "Newgirl's Punishment choice remain unchanged."
            if kind == "easy_target_child" and detail.get("hurt_cohort_missed")
            else "After Handler validation and before the NPC performs the bodily action, "
            "record how your own present body actually goes along, or decline. Actual "
            "participation exempts both from the matching Easy Target Punishment only. "
            "The NPC must still perform, and the Newgirl owns the actual injury choice; "
            "no roll, free defense or immunity from damage is granted."
            if kind == "easy_target_child" and detail.get("hurt_cohort")
            else "This protection already failed before your participation was recorded. "
            "Acknowledge the missed opportunity to close your pending obligation without "
            "exemption. The original failure and Newgirl's Tag choice remain unchanged."
            if kind == "easy_target_child" and detail.get("protection_cohort_missed")
            else "After the original NPC has actually performed protection, record how your own "
            "person went along. Both avoid Easy Target consequences; this grants no roll, "
            "bonus, interception or injury. After Handler validation you may instead decline, "
            "even before the NPC performs, without an exemption. Prior failures cannot be erased."
            if kind == "easy_target_child" and detail.get("protection_cohort")
            else "This use has already finished. Acknowledge your own missed participation. "
            "This grants no exemption and cannot erase the original consequence or Bond choice."
            if kind == "easy_target_child" and detail.get("use_cohort_missed")
            else "After Handler validation, record your actual participation while the original "
            "person's non-Play use is ongoing. That person then records completion; both avoid the "
            "Easy Target Bond consequence. You may instead decline without an exemption. "
            "This invents no roll, effect or consent."
            if kind == "easy_target_child" and detail.get("use_cohort")
            else "Record your original Handler's actual completed non-Play use. "
            "The original Newgirl then chooses whether to deepen their Bond unless a cohort "
            "actually participated. Unanswered cohorts must acknowledge their own missed "
            "participation after you finish. This invents no roll, payment, injury, consent "
            "or other mechanical effect. "
            "A separately triggered Play still requires its actual source."
            if kind == "easy_target_child" and detail.get("handler_use")
            else "Validate only the original Handler's ordinary non-Play use. "
            "This cannot replace consent or any separately triggered Play, payment or injury."
            if kind == "easy_target_validate" and detail.get("handler_use")
            else "Record your original Handler's actual protective action. This creates no "
            "roll, interception, bonus or injury. The original Newgirl owns the optional "
            "Tag after source-proved failure; separately triggered Plays remain required."
            if kind == "easy_target_child" and detail.get("handler_protect")
            else "Validate the original ordinary Handler's actual non-Play protective task. "
            "Your real present body and original source remain required. This invents no "
            "free defense, injury or permission to answer the Newgirl's later Tag choice."
            if kind == "easy_target_validate" and detail.get("handler_protect")
            else "Record your original Girl's actual protective action. This creates no roll, "
            "interception, bonus or injury. The original Newgirl owns the optional Tag after "
            "source-proved failure; separately triggered Plays remain required."
            if kind == "easy_target_child" and detail.get("pilot_protect")
            else "Validate the original Girl's actual non-Play protective task and available "
            "present body. This creates no free defense or injury and does not grant anyone "
            "else permission to choose her performance or the Newgirl's later Tag."
            if kind == "easy_target_validate" and detail.get("pilot_protect")
            else "Record your original Girl's actual completed non-Play use. The original "
            "Newgirl then owns the optional Bond choice unless a cohort actually participated. "
            "This creates no roll, injury, payment, consent or other mechanical effect. "
            "A separately triggered Play still requires its actual source."
            if kind == "easy_target_child" and detail.get("pilot_use")
            else "Validate only this original Girl's ordinary non-Play use and actual present "
            "exterior body. This cannot replace consent, a triggered Play or a required effect."
            if kind == "easy_target_validate" and detail.get("pilot_use")
            else "Record the actual completed non-Play use by your NPC. This creates no roll, "
            "injury, payment, or consent. The original Newgirl then owns the optional Bond "
            "choice unless a cohort actually participated. Unanswered cohorts remain pending "
            "for their own missed-participation acknowledgment after you finish. If a Play is "
            "triggered, use its actual source instead."
            if kind == "easy_target_child" and detail.get("npc_use")
            else "Validate only actual ordinary NPC use that triggers no separate Play or "
            "mechanical effect. This account cannot replace consent, an actual rolled source, "
            "payment, injury or any other required workflow."
            if kind == "easy_target_validate" and detail.get("npc_use")
            else "Record the actual NPC's bodily action you performed. The original Newgirl "
            "then selects the actual Girl Asset injury; physical interception and all "
            "ordinary consequences remain real. This is not a PC Play or a roll."
            if kind == "easy_target_child" and detail.get("npc_hurt")
            else "Validate the actual supported one-Asset bodily injury and physical source; "
            "this account cannot invent harm, an NPC roll, or damage an inaccessible body."
            if kind == "easy_target_validate" and detail.get("npc_hurt")
            else "Record only the actual NPC protective action you performed. This creates no "
            "roll, interception, bonus or injury. The Newgirl may give your NPC a Tag after "
            "a source-proved failure; OOC pause remains available."
            if kind == "easy_target_child" and detail.get("npc_protect")
            else "Validate the actual NPC protective task and source. Performance remains the "
            "NPC controller's own factual account, without an NPC roll or free defense."
            if kind == "easy_target_validate" and detail.get("npc_protect")
            else "Actual fictional urge and performed consequences; OOC pause remains available."
        ),
        fields,
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)


async def open_easy_target(
    interaction: discord.Interaction, service: EasyTargetService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    form: NativeForm
    if identity is not None:
        shown = await asyncio.to_thread(service.view, viewer, identity)
        if shown.get("can_failure_tag"):

            async def failure(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.failure_tag,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    shown["revision"],
                    values["give"][0] == "yes",
                    values["account"],
                )
                return "Your actual optional protection-failure Tag choice is saved."

            async def failure_access(current: discord.Interaction) -> None:
                await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

            fact = shown.get("protection_failure")
            context = (
                (
                    "\nAttempted prevention: "
                    + fact["attempt"]
                    + "\nActual occurrence: "
                    + fact["occurred"]
                )
                if fact
                else ""
            )
            form = MemoryForm(
                interaction.user.id,
                "Actual protection failure",
                "Your original protector failed after source-proved harm or a factual Handler "
                "decision. You own this optional Tag." + context,
                [
                    Field(
                        "give",
                        "Give a Tag to the original protector?",
                        (("yes", "Give a Tag"), ("no", "Decline")),
                    ),
                    Field("account", "Actual Tag label, or your explicit decline", paragraph=True),
                ],
                failure,
                authorize=failure_access,
            )
            await reply(interaction, form.text(), form)
            return
        if shown.get("can_report_failure"):

            async def report(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.fail_protection,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    shown["revision"],
                    values["attempt"],
                    values["occurred"],
                )
                return "Your actual source-bound protection-failure decision is saved."

            async def report_access(current: discord.Interaction) -> None:
                await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

            form = MemoryForm(
                interaction.user.id,
                "Actual protection failure",
                "As the original Handler, record the attempted prevention and what actually "
                "occurred without inventing mechanical harm. This grants only the original "
                "Newgirl's optional failure Tag; no bodily damage or other outcome is applied."
                + "\nActual protective performance: "
                + shown["npc_protection"]["account"],
                [
                    Field("attempt", "Actual attempted prevention", paragraph=True),
                    Field("occurred", "Actual nonmechanical occurrence", paragraph=True),
                ],
                report,
                authorize=report_access,
            )
            await reply(interaction, form.text(), form)
            return
        if shown["pending"]:
            await open_choice(interaction, service.game, shown["pending"][0]["id"])
            return
        work = shown["work"]
        history = "".join(
            "\nNPC performance: "
            + x["account"]
            + "\nInjury: "
            + (x["asset"] or "waiting for actual owned selection")
            + ("; actual attempt resolved" if x["completed_event"] else "; pending")
            for x in shown.get("npc_hurt", ())
        )
        history += "".join(
            "\nActual Girl use: " + x["account"]
            for x in shown.get("npc_use", ())
            if x["actor"]["kind"] == "pilot"
        )
        history += "".join(
            "\nHurt participation: " + x["outcome"] + "\n" + x["account"]
            for x in shown.get("hurt_cohort", ())
        )
        history += "".join(
            "\nProtection participation: " + x["outcome"] + "\n" + x["account"]
            for x in shown.get("protection_cohort", ())
        )
        protection = shown.get("npc_protection")
        failed = shown.get("protection_failure")
        if protection:
            history += "\nActual protection: " + protection["account"]
        if failed:
            history += "\nAttempted prevention: " + failed["attempt"]
            history += "\nActual occurrence: " + failed["occurred"]

        async def history_access(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        text = (
            work["urge"]
            + ": "
            + work["account"]
            + "\n"
            + (
                work["consequence"]
                or (
                    "Performed; protection remains active"
                    if work["protection_event"]
                    else "Waiting for actual required performance"
                )
            )
            + history
        )
        history_view = MemoryHistory(interaction.user.id, text, history_access)
        await reply(interaction, history_view.text(), history_view)
        return
    data = await asyncio.to_thread(service.menu, viewer, int(interaction.channel_id or 0))
    options = [(x["id"], x["label"]) for x in data["tasks"]]
    if data.get("can_start"):
        options.insert(0, ("start", "Actual mistake: Easy Target"))
    if not options:
        await reply(interaction, "No owned Easy Target source or available actual Newgirl here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        if values["source"][0] != "start":
            await open_easy_target(current, service, values["source"][0])
            return
        sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(current))

        async def begin(response: discord.Interaction, answer: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(response),
                str(response.id),
                data["channel"],
                sheet["revision"],
                PlayInput(
                    play="easy_target",
                    heat=int(answer["heat"][0]),
                    context=answer["context"],
                    trigger_confirmed=True,
                ),
            )
            return "Actual Easy Target prepared: " + str(result["action_id"])

        form = NativeForm(
            current.user.id,
            "Easy Target",
            "Describe your actual mistake in the real scene.",
            [
                Field("heat", "Actual Heat to spend", tuple((str(x), str(x)) for x in range(1, 6))),
                Field("context", "Actual mistake or stupid statement", paragraph=True),
            ],
            begin,
        )
        await reply(current, form.text(), form)

    form = NativeForm(
        interaction.user.id,
        "Easy Target",
        "Private original choices and durable actual history.",
        [Field("source", "Actual source", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
