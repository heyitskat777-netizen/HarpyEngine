"""Owner-bound scene roles; joining never claims travel, consent or piloting."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_actors import LABELS
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_journalist import Job
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_conditioning import ConditioningService
from girlframe.services.m3_harpy_creation import HarpyCreationService
from girlframe.services.m3_npc_handover import LABELS as HANDOVER_LABELS
from girlframe.services.m3_npc_handover import Job as HandoverJob
from girlframe.services.onboarding import WorkflowError

NPC_REQUEST_LABELS: dict[Job, str] = {
    "journalist": "Ask a direct question as ",
    "family": "Point out a change as ",
    "psychologist": "Give a directive as ",
    "public_relations": "Set an expectation as ",
}


async def open_cast(interaction: discord.Interaction, service: CastService) -> None:
    viewer, channel = viewer_from_interaction(interaction), interaction.channel_id
    if channel is None:
        await reply(interaction, "Open scene roles in its bound server channel.")
        return
    data = await asyncio.to_thread(service.view, viewer, channel)
    owned = await asyncio.to_thread(service.actors.choices, viewer)
    own_cast = {x["token"]: x for x in data["roles"] if x.get("own")}
    options: list[tuple[str, str]] = []
    actions: dict[str, tuple[str, ActorRef | None]] = {}
    npc_requests: dict[str, tuple[Job, ActorRef]] = {}
    handovers: dict[str, tuple[HandoverJob, ActorRef]] = {}
    prompt_roles = {}
    for role in owned["actors"]:
        if role["token"] not in own_cast:
            token = "join:" + role["token"]
            options.append(
                (token, "Join as " + role["label"][:60] + " (" + LABELS[role["kind"]] + ")")
            )
            actions[token] = ("join", ActorRef.model_validate(role["ref"]))
    for token, role in own_cast.items():
        key = "withdraw:" + token
        options.append((key, "Withdraw " + role["label"][:75]))
        actions[key] = ("withdraw", ActorRef.model_validate(role["ref"]))
        if role.get("only_she_matters"):
            key = "only-she:" + token
            options.append((key, "Use Only She Matters as " + role["label"][:55]))
            actions[key] = ("only_she", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_song"):
            key = "song:" + token
            options.append((key, "Sing A Song of Love Lost as " + role["label"][:54]))
            actions[key] = ("harpy_song", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_eagle"):
            key = "eagle:" + token
            options.append((key, "Use Eagle Cracks the Shell as " + role["label"][:50]))
            actions[key] = ("harpy_eagle", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_kiss"):
            key = "kiss:" + token
            options.append((key, "Use Kiss Me, Darling as " + role["label"][:58]))
            actions[key] = ("harpy_kiss", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_intimacy"):
            key = "intimacy:" + token
            options.append((key, "Open a private Harpy invitation as " + role["label"][:50]))
            actions[key] = ("harpy_intimacy", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_gaze"):
            key = "gaze:" + token
            options.append((key, "Use Manic Pixie Dream Monster as " + role["label"][:49]))
            actions[key] = ("harpy_gaze", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_visions"):
            key = "visions:" + token
            options.append((key, "Use Visions of Infinity as " + role["label"][:52]))
            actions[key] = ("harpy_visions", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_rewrite"):
            key = "rewrite:" + token
            options.append((key, "Propose the one-minute edit as " + role["label"][:55]))
            actions[key] = ("harpy_rewrite", ActorRef.model_validate(role["ref"]))
        if role.get("harpy_mask"):
            key = "mask:" + token
            options.append((key, "Use A Human Mask as " + role["label"][:65]))
            actions[key] = ("harpy_mask", ActorRef.model_validate(role["ref"]))
        if role.get("ancillary_intimacy"):
            key = "ancillary-private-play:" + token
            options.append((key, "Open a private invitation as " + role["label"][:50]))
            actions[key] = ("ancillary_intimacy", ActorRef.model_validate(role["ref"]))
        if role.get("chained_placement"):
            key = "chained-placement:" + token
            options.append((key, "Record placement for " + role["label"][:62]))
            actions[key] = ("chained_placement", ActorRef.model_validate(role["ref"]))
        if role.get("chronically_online"):
            key = "recollection:" + token
            options.append((key, "Recall prior Pilot facts as " + role["label"][:58]))
            actions[key] = ("chronically_online", ActorRef.model_validate(role["ref"]))
        if role.get("debt_contact"):
            key = "debt-contact:" + token
            options.append((key, "Manage cash offers to " + role["label"][:58]))
            actions[key] = ("debt_contact", ActorRef.model_validate(role["ref"]))
        if role.get("mercenary_debt"):
            key = "debt:" + token
            options.append((key, "Offer cash as " + role["label"][:65]))
            actions[key] = ("mercenary_debt", ActorRef.model_validate(role["ref"]))
        if role.get("patronage"):
            key = "patronage:" + token
            options.append((key, "Review Patron funding for " + role["label"][:60]))
            actions[key] = ("patronage", ActorRef.model_validate(role["ref"]))
        if role.get("abysstech"):
            key = "abysstech:" + token
            options.append((key, "Use Experimental Abysstech as " + role["label"][:56]))
            actions[key] = ("abysstech", ActorRef.model_validate(role["ref"]))
        if role.get("escape_source"):
            key = "escape:" + token
            options.append((key, "Start Escape as " + role["label"][:65]))
            actions[key] = ("escape", ActorRef.model_validate(role["ref"]))
        if role.get("director_phone"):
            phone = "phone:" + token
            options.append((phone, "Call the Handler as " + role["label"][:55]))
            actions[phone] = ("phone", ActorRef.model_validate(role["ref"]))
        if role.get("job_prompts"):
            prompt_key = "prompts:" + token
            options.append((prompt_key, "Review job prompts for " + role["label"][:65]))
            prompt_roles[prompt_key] = token
            jobs_key = "jobs:" + token
            options.append((jobs_key, "Change jobs for " + role["label"][:65]))
            actions[jobs_key] = ("jobs", ActorRef.model_validate(role["ref"]))
            for job, label in NPC_REQUEST_LABELS.items():
                if job in role["job_prompts"]:
                    request = job + ":" + token
                    options.append((request, label + role["label"][:55]))
                    npc_requests[request] = (job, ActorRef.model_validate(role["ref"]))
            for handover, label in HANDOVER_LABELS.items():
                if handover in role["job_prompts"]:
                    key = "handover:" + handover + ":" + token
                    options.append((key, label))
                    handovers[key] = (handover, ActorRef.model_validate(role["ref"]))
            if "handler" in role["job_prompts"]:
                order = "npc-handler-order:" + token
                options.append((order, "Send a Girl as " + role["label"][:60]))
                actions[order] = ("npc_handler_order", ActorRef.model_validate(role["ref"]))
            if "intelligence_agent" in role["job_prompts"]:
                inquiry = "npc-intelligence:" + token
                options.append((inquiry, "Investigate as " + role["label"][:60]))
                actions[inquiry] = ("npc_intelligence", ActorRef.model_validate(role["ref"]))
    if data["may_facilitate"] and not data["own_facilitator"]:
        options.append(("facilitate", "Join as facilitator (no fictional character)"))
        actions["facilitate"] = ("facilitate", None)
    for role in data["roles"]:
        if role.get("capture_source"):
            key = "capture:" + role["token"]
            options.append((key, "Record a capture at the Rebel base"))
            actions[key] = ("captured", ActorRef.model_validate(role["ref"]))
    if data["own_facilitator"]:
        options.append(("withdraw_facilitator", "Stop facilitating this scene"))
        actions["withdraw_facilitator"] = ("withdraw_facilitator", None)
    for role in data["adjudicator_options"]:
        key = "adjudicate:" + role["token"]
        options.append((key, "Offer " + role["label"][:55] + " for Handler-rule responses"))
        actions[key] = ("adjudicate", ActorRef.model_validate(role["ref"]))
    conditioning = ConditioningService(service.game)
    harpy_creation = HarpyCreationService(service.game)
    if data["own_facilitator"]:
        try:
            invitation = await asyncio.to_thread(harpy_creation.menu, viewer)
        except WorkflowError:
            pass
        else:
            if invitation["members"]:
                options.append(("invite-harpy", "Invite a new Harpy controller"))
    try:
        if conditioning.enabled():
            await asyncio.to_thread(conditioning.menu, viewer, channel)
            options.append(("conditioning", "Request private Conditioning"))
            speech = await asyncio.to_thread(conditioning.speech, viewer, channel)
            if speech["sources"]:
                options.append(("conditioning-word", "Speak a private Conditioning word"))
    except WorkflowError:
        pass

    async def prompt_role(current: discord.Interaction, key: str) -> dict[str, Any]:
        roles: list[dict[str, Any]] = (
            await asyncio.to_thread(service.view, viewer_from_interaction(current), channel)
        )["roles"]
        role = next(
            (x for x in roles if x["token"] == prompt_roles[key] and x.get("job_prompts")), None
        )
        if role is None:
            raise WorkflowError("Reopen your current original NPC role.")
        return role

    async def choose(current: discord.Interaction, token: str) -> None:
        if token == "invite-harpy":
            from girlframe.discord_adapter.m3_harpy_creation import open_invitation

            await open_invitation(current, harpy_creation)
            return
        if token == "conditioning":
            from girlframe.discord_adapter.m3_conditioning import open_invite

            await open_invite(current, conditioning, channel)
            return
        if token == "conditioning-word":
            from girlframe.discord_adapter.m3_conditioning import open_speech

            await open_speech(current, conditioning, channel)
            return
        if token in prompt_roles:
            role = await prompt_role(current, token)

            async def show_job(click: discord.Interaction, job: str) -> None:
                latest = await prompt_role(click, token)
                prompts = latest["job_prompts"].get(job)
                if not prompts:
                    raise WorkflowError("Reopen the original NPC's current jobs.")
                await reply(
                    click,
                    "**"
                    + clean(latest["label"])
                    + " · "
                    + job.replace("_", " ").title()
                    + "**\n"
                    + "\n".join("• " + prompt for prompt in prompts)
                    + "\nUse the scene's normal authority to resolve any effects.",
                )

            jobs = tuple((job, job.replace("_", " ").title()) for job in role["job_prompts"])
            if len(jobs) == 1:
                await show_job(current, jobs[0][0])
            else:
                await Picker(
                    viewer.user_id, "Choose one of this NPC's current jobs.", jobs, show_job
                ).show(current)
            return
        if token in npc_requests:
            from girlframe.discord_adapter.m3_journalist import open_ask
            from girlframe.services.m3_journalist import JournalistService

            requested_job, requester = npc_requests[token]
            await open_ask(
                current, JournalistService(service.game), channel, requester, job=requested_job
            )
            return
        if token in handovers:
            from girlframe.discord_adapter.m3_npc_handover import open_handover
            from girlframe.services.m3_npc_handover import NpcHandoverService

            handover, npc = handovers[token]
            await open_handover(current, NpcHandoverService(service.game), channel, npc, handover)
            return
        action, ref = actions[token]
        if action == "only_she":
            from girlframe.discord_adapter.m3_harpy_only_she import open_only_she
            from girlframe.services.m3_harpy_only_she import OnlySheMattersService

            assert ref is not None
            await open_only_she(current, OnlySheMattersService(service.game), channel, ref)
            return
        if action == "harpy_song":
            from girlframe.discord_adapter.m3_harpy_song import open_song
            from girlframe.services.m3_harpy_song import HarpySongService

            assert ref is not None
            await open_song(current, HarpySongService(service.game), channel, ref)
            return
        if action == "harpy_eagle":
            from girlframe.discord_adapter.m3_harpy_eagle import open_eagle
            from girlframe.services.m3_harpy_eagle import EagleService

            assert ref is not None
            await open_eagle(current, EagleService(service.game), channel, ref)
            return
        if action == "harpy_kiss":
            from girlframe.discord_adapter.m3_harpy_kiss import open_kiss
            from girlframe.services.m3_harpy_kiss import KissService

            assert ref is not None
            await open_kiss(current, KissService(service.game), channel, ref)
            return
        if action == "harpy_intimacy":
            from girlframe.discord_adapter.m3_harpy_intimacy import open_intimacy
            from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService

            assert ref is not None
            await open_intimacy(current, HarpyIntimacyService(service.game), channel, ref)
            return
        if action == "harpy_gaze":
            from girlframe.discord_adapter.m3_harpy_gaze import open_gaze
            from girlframe.services.m3_harpy_gaze import GazeService

            assert ref is not None
            await open_gaze(current, GazeService(service.game), channel, ref)
            return
        if action == "harpy_visions":
            from girlframe.discord_adapter.m3_harpy_visions import open_visions
            from girlframe.services.m3_harpy_visions import VisionsService

            assert ref is not None
            await open_visions(current, VisionsService(service.game), channel, ref)
            return
        if action == "harpy_rewrite":
            from girlframe.discord_adapter.m3_harpy_rewrite import open_rewrite
            from girlframe.services.m3_harpy_rewrite import RewriteService

            assert ref is not None
            await open_rewrite(current, RewriteService(service.game), channel, ref)
            return
        if action == "harpy_mask":
            from girlframe.discord_adapter.m3_harpy_mask import open_mask
            from girlframe.services.m3_harpy_mask import MaskService

            assert ref is not None
            await open_mask(current, MaskService(service.game), channel, ref)
            return
        if action == "captured":
            from girlframe.discord_adapter.m3_captured import open_capture
            from girlframe.services.m3_captured import CapturedService

            assert ref is not None
            await open_capture(current, CapturedService(service.game), channel, ref)
            return
        if action == "ancillary_intimacy":
            from girlframe.discord_adapter.m3_ancillary_intimacy import open_ancillary_intimacy
            from girlframe.services.m3_ancillary_intimacy import AncillaryIntimacyService

            assert ref is not None
            await open_ancillary_intimacy(
                current, AncillaryIntimacyService(service.game), channel, ref
            )
            return
        if action == "chained_placement":
            from girlframe.discord_adapter.m3_chained_darling import open_chained_placement
            from girlframe.services.m3_chained_darling import ChainedPlacementService

            assert ref is not None
            await open_chained_placement(
                current, ChainedPlacementService(service.game), channel, ref
            )
            return
        if action == "chronically_online":
            from girlframe.discord_adapter.m3_chronically_online import open_recollection
            from girlframe.services.m3_chronically_online import ChronicallyOnlineService

            assert ref is not None
            await open_recollection(current, ChronicallyOnlineService(service.game), channel, ref)
            return
        if action == "debt_contact":
            from girlframe.discord_adapter.m3_mercenary_debt import open_debt_contact
            from girlframe.services.m3_mercenary_debt import DebtService

            assert ref is not None
            await open_debt_contact(current, DebtService(service.game), channel, ref)
            return
        if action == "mercenary_debt":
            from girlframe.discord_adapter.m3_mercenary_debt import open_debt
            from girlframe.services.m3_mercenary_debt import DebtService

            assert ref is not None
            await open_debt(current, DebtService(service.game), channel, ref)
            return
        if action == "patronage":
            from girlframe.discord_adapter.m3_mercenary_patron import open_patron
            from girlframe.services.m3_mercenary_patron import MercenaryPatronService

            assert ref is not None
            await open_patron(current, MercenaryPatronService(service.game), channel, ref)
            return
        if action == "abysstech":
            from girlframe.discord_adapter.m3_abysstech import open_abysstech
            from girlframe.services.m3_abysstech import AbysstechService

            assert ref is not None
            await open_abysstech(current, AbysstechService(service.game), channel, ref)
            return
        if action == "escape":
            from girlframe.discord_adapter.m3_escape import open_escape
            from girlframe.services.m3_escape import EscapeService

            assert ref is not None
            await open_escape(current, EscapeService(service.game), channel, ref)
            return
        if action == "npc_handler_order":
            from girlframe.discord_adapter.m3_npc_orders import open_handler_order
            from girlframe.services.m3_npc_orders import NpcOrderService

            assert ref is not None
            await open_handler_order(current, NpcOrderService(service.game), channel, ref)
            return
        if action == "npc_intelligence":
            from girlframe.discord_adapter.m3_npc_intelligence import open_inquiry
            from girlframe.services.m3_npc_intelligence import IntelligenceService

            assert ref is not None
            await open_inquiry(current, IntelligenceService(service.game), channel, ref)
            return
        if action == "phone":
            from girlframe.discord_adapter.m3_director_strain import open_phone
            from girlframe.services.m3_director_strain import DirectorStrainService
            from girlframe.services.m3_off_duty import OffDutyService
            from girlframe.services.m3_strain import StrainService

            assert ref is not None
            phone_service = DirectorStrainService(
                StrainService(OffDutyService(service.actors.missions))
            )
            await open_phone(current, phone_service, channel, ref)
            return
        if action == "jobs":
            from girlframe.services.m3_npc_roles import NpcRoleService
            from girlframe.services.m3_world import WorldService

            assert ref is not None
            npc_roles = NpcRoleService(WorldService(service.actors.missions))
            job_data = await asyncio.to_thread(
                npc_roles.jobs, viewer_from_interaction(current), channel, ref
            )

            async def save_jobs(click: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    npc_roles.change_jobs,
                    viewer_from_interaction(click),
                    str(click.id),
                    channel,
                    job_data["revision"],
                    ref,
                    values.get("jobs", ()),
                    values["account"],
                )
                return "The NPC's current jobs are saved."

            form = NativeForm(
                viewer.user_id,
                "Change this NPC's jobs",
                "Record the actual change in the scene.",
                [
                    Field(
                        "jobs",
                        "Current ordinary jobs",
                        job_data["options"],
                        0 if job_data["fixed"] else 1,
                        len(job_data["options"]),
                        required=not job_data["fixed"],
                    ),
                    Field("account", "What changed?", paragraph=True),
                ],
                save_jobs,
                values={"jobs": job_data["jobs"]},
            )
            await reply(current, form.text(), form)
            return

        async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.change,
                viewer_from_interaction(actor),
                str(actor.id),
                channel,
                data["game_revision"],
                data["cast_revision"],
                action,
                ref,
            )
            return "Your scene role is saved. Reopen /mission cast to review it."

        form = NativeForm(
            viewer.user_id,
            "Confirm scene role",
            dict(options)[token] + ". This records who you control in the scene. "
            "Fictional location, piloting and consent need their own rules.",
            [Field("confirm", "Confirm", (("yes", "Save this scene role"),))],
            submit,
        )
        await reply(current, form.text(), form)

    text = "**Scene roles**\n" + "\n".join(x["label"] for x in data["roles"])
    text += "\nFacilitating and playing the Handler are separate roles."
    if data["adjudicator_selected"]:
        text += "\nA Director is selected for Handler-rule responses."
    if not options:
        await reply(interaction, text[:1800])
        return
    await Picker(viewer.user_id, text[:1600], tuple(options), choose).show(interaction)
