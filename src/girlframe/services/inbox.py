"""Complete private aggregation with derived role-specific coordination tasks."""

import hashlib
import json
from datetime import datetime

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.engine.bonds import starting_kind
from girlframe.engine.creation_details import GirlDetails
from girlframe.engine.inbox import CATEGORIES, SCOPES, InboxItem, InboxPage
from girlframe.services.bonds import BondService, Decision
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService


class InboxService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.bonds, self.shared = BondService(store), SharedSetupService(store)
        self.coordination = CoordinationService(store)

    def items(self, viewer: GuildViewer) -> tuple[InboxItem, ...]:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")  # One read snapshot across sources and tasks.
            self.bonds._authorize(connection, viewer)
            user = str(viewer.user_id)
            bonds = self.bonds._latest(connection, user)
            shared = self.shared._latest(connection, viewer.user_id)
            coordinated = self.coordination._latest(connection, viewer.user_id)
            events = [x["event_id"] for x in bonds + shared + coordinated]
            times = {
                str(identity): str(stamp)
                for identity, stamp in connection.execute(
                    sa.select(t.events.c.id, t.events.c.created_utc).where(
                        t.events.c.campaign_id == self.store.campaign_id, t.events.c.id.in_(events)
                    )
                ).all()
            }
            # Project public aliases only, never another character's private body.
            profiles = {
                int(uid): json.loads(body)
                for uid, body in connection.execute(
                    sa.select(t.characters.c.user_id, t.characters.c.public_json).where(
                        t.characters.c.campaign_id == self.store.campaign_id
                    )
                )
            }

            def label(uid: str | int) -> str:
                return (
                    str(profiles.get(int(uid), {}).get("callsign", "Player"))
                    + " ("
                    + str(uid)
                    + ")"
                )

            items: list[InboxItem] = []
            for row in bonds:
                incoming = row["target_id"] == user
                stale = self.bonds._stale(connection, row)
                girl = row["girl_playbook"]
                category = (
                    "mentors" if girl == "NEWGIRL" else "pair" if girl == "BONDED" else "bonds"
                )
                title = (
                    "Mentor agreement"
                    if girl == "NEWGIRL"
                    else "Pair agreement"
                    if girl == "BONDED"
                    else "Starting Bond"
                )
                pending = row["state"] == "pending"
                primary = "Accept agreement" if pending and incoming else None
                secondary = (
                    "decline"
                    if pending and incoming
                    else "withdraw"
                    if pending or row["state"] == "accepted"
                    else None
                )
                effect = f"Save a mutual {starting_kind(girl)} starting agreement. No Play runs."
                details = row["context"] or "No shared context provided."
                if girl == "NEWGIRL":
                    details += (
                        "\nHandler-nominated Mentor: chooses callsign and counts as higher Status."
                    )
                if girl == "BONDED":
                    details += "\nPair chooses Girl Asset names; owner writes descriptions."
                if girl == "AM":
                    details += "\nAM counterpart: this Girl is Jailbroken."
                items.append(
                    InboxItem(
                        "bond:" + row["id"],
                        "bond",
                        row["id"],
                        row["revision"],
                        category,
                        title,
                        label(row["source_id"] if incoming else row["target_id"]),
                        row["state"],
                        incoming,
                        stale,
                        effect,
                        details,
                        primary,
                        secondary,
                        sort_time=times.get(row["event_id"], ""),
                    )
                )
            for row in shared:
                incoming = row["target_id"] == user
                court = row["kind"] == "court"
                pending = row["state"] == "pending"
                value = str(next(iter(json.loads(row["choice_json"]).values())))
                effect = (
                    "Assign this AM to the recipient and keep four on the pilot. Setup only."
                    if court
                    else "Save the Mentor callsign for activation; current nickname is unchanged."
                )
                items.append(
                    InboxItem(
                        "shared:" + row["id"],
                        "shared",
                        row["id"],
                        row["revision"],
                        "court" if court else "mentors",
                        "Red Queen's Court" if court else "Mentor callsign",
                        label(row["source_id"] if incoming else row["target_id"]),
                        row["state"],
                        incoming,
                        self.shared._stale(connection, row),
                        effect,
                        value,
                        "Accept setup" if pending and incoming else None,
                        "decline"
                        if pending and incoming
                        else "withdraw"
                        if pending or row["state"] == "accepted"
                        else None,
                        sort_time=times.get(row["event_id"], ""),
                    )
                )

            for row in coordinated:
                incoming = row["owner_id"] == user
                pending = row["state"] == "pending"
                parsed = self.coordination.parsed(row)
                title = (
                    "Handler investor desires"
                    if row["role"] == "vatgrown_handler"
                    else "Princess Handler standard"
                    if row["role"] == "princess_handler"
                    else "Princess bonded-Girl standard"
                )
                items.append(
                    InboxItem(
                        "coordination:" + row["id"],
                        "coordination",
                        row["id"],
                        row["revision"],
                        "playbook",
                        title,
                        label(row["author_id"] if incoming else row["owner_id"]),
                        row["state"],
                        incoming,
                        self.coordination._stale(connection, row),
                        "Save this chooser's setup choice. No Play or fictional consequence runs.",
                        parsed.label,
                        "Accept choice" if pending and incoming else None,
                        "decline"
                        if pending and incoming
                        else "withdraw"
                        if pending or row["state"] == "accepted"
                        else None,
                        sort_time=times.get(row["event_id"], ""),
                    )
                )

            def has_shared(kind: str, target: int | None = None) -> bool:
                return any(
                    x["source_id"] == user
                    and x["kind"] == kind
                    and (target is None or int(x["target_id"]) == target)
                    and x["state"] in ("pending", "accepted")
                    and not self.shared._stale(connection, x)
                    for x in shared
                )

            def task(
                key: str,
                category: str,
                title: str,
                other: int | None,
                effect: str,
                action: str,
                route: str,
                revision: int = 0,
            ) -> None:
                items.append(
                    InboxItem(
                        "task:" + key,
                        "task",
                        key,
                        revision,
                        category,
                        title,
                        label(other) if other else "Your character",
                        "pending",
                        True,
                        False,
                        effect,
                        "Continue the authorized wizard. Opening a task saves nothing.",
                        action,
                        task=route,
                        target=other,
                    )
                )

            handler = HandlerService(self.store)
            nomination = handler.mentor_for(connection, viewer.user_id)
            if nomination:
                present = any(
                    x["source_id"] == user
                    and int(x["target_id"]) == nomination.mentor.user_id
                    and x["girl_playbook"] == "NEWGIRL"
                    and x["state"] in ("pending", "accepted")
                    and not self.bonds._stale(connection, x)
                    for x in bonds
                )
                if not present:
                    task(
                        "mentor:" + nomination.assignment_id,
                        "mentors",
                        "Start Mentor agreement",
                        nomination.mentor.user_id,
                        "Review a Bond with the nominated Mentor; the Mentor then accepts.",
                        "Start agreement",
                        "mentor_start",
                    )
            for row in bonds:
                if row["state"] != "accepted" or self.bonds._stale(connection, row):
                    continue
                if (
                    row["girl_playbook"] == "NEWGIRL"
                    and row["target_id"] == user
                    and not has_shared("callsign", int(row["source_id"]))
                ):
                    task(
                        "name:" + row["id"],
                        "mentors",
                        "Choose Newgirl callsign",
                        int(row["source_id"]),
                        "As accepted Mentor, propose a callsign for Newgirl to review.",
                        "Enter callsign",
                        "callsign",
                        row["revision"],
                    )
                if row["girl_playbook"] == "BONDED":
                    choice = PairService(self.store)._choice(connection, row)
                    if row["target_id"] == user and not choice.names:
                        task(
                            "assets:" + row["id"],
                            "pair",
                            "Choose Pair Assets",
                            int(row["source_id"]),
                            "Choose two Girl Asset names. The owner supplies private descriptions.",
                            "Choose Assets",
                            "pair",
                            row["revision"],
                        )
                    elif row["source_id"] == user and choice.names:
                        progress = CreationService(self.store)._current(connection, viewer)
                        described = {
                            x.name
                            for x in progress.draft.pair_asset_descriptions
                            if x.description.strip()
                        }
                        if described != set(choice.names):
                            task(
                                "describe:" + choice.token,
                                "pair",
                                "Describe Pair-selected Assets",
                                int(row["target_id"]),
                                "Describe the Pair-selected names and save your draft.",
                                "Open builder",
                                "describe",
                                choice.revision,
                            )
            own = profiles.get(viewer.user_id)
            for entry in self.coordination.tasks(connection, viewer):
                digest = hashlib.sha256(
                    json.dumps(entry["context"], sort_keys=True).encode()
                ).hexdigest()[:24]
                task(
                    "coordination:" + entry["role"] + ":" + str(entry["owner"]) + ":" + digest,
                    "playbook",
                    "Choose Handler investor desires"
                    if entry["role"] == "vatgrown_handler"
                    else "Choose Princess standard",
                    entry["owner"],
                    "Choose your required playbook option for the owner's private review.",
                    "Choose options",
                    "coordinate",
                )
            if (
                own
                and own["girl_playbook"] in ("PRINCESS", "OLDGEN", "VATGROWN")
                and handler.current(connection)[1].handler_id != viewer.user_id
            ):
                progress = CreationService(self.store)._current(connection, viewer)
                details = progress.draft.girl_details or GirlDetails()
                missing = (
                    details.own_standard is None
                    if own["girl_playbook"] == "PRINCESS"
                    else len(details.maxims) != 2
                    if own["girl_playbook"] == "OLDGEN"
                    else not progress.draft.npc_bonds
                    or {x.npc_slot for x in details.investors}
                    != {x.slot for x in progress.draft.npc_bonds}
                )
                if missing:
                    task(
                        "details:" + str(viewer.user_id),
                        "playbook",
                        "Complete your Girl setup",
                        None,
                        "Choose your standard, maxims or NPC desires; then Save progress.",
                        "Open Girl setup",
                        "girl_details",
                        progress.revision,
                    )
            if (
                own
                and own["girl_playbook"] == "NEWGIRL"
                and handler.current(connection)[1].handler_id != viewer.user_id
            ):
                progress = CreationService(self.store)._current(connection, viewer)
                cadre = handler.cadre(connection, viewer.user_id)
                declared = {x.user_id: x.character_revision for x in progress.draft.prior_missions}
                if not progress.draft.cadre_discussed or not cadre or declared != cadre:
                    task(
                        "missions:" + str(viewer.user_id),
                        "mentors",
                        "Declare Cadre mission history",
                        None,
                        "Choose zero or one shared mission per counterpart and confirm discussion.",
                        "Review mission history",
                        "history",
                        progress.revision,
                    )
            if (
                own
                and own["frame_playbook"] == "THE RED QUEEN"
                and handler.current(connection)[1].handler_id != viewer.user_id
                and not has_shared("court")
            ):
                task(
                    "court:" + str(viewer.user_id),
                    "court",
                    "Choose starting Court assignment",
                    None,
                    "Choose the other Girl and external AM. Four stay on you; recipient reviews.",
                    "Choose recipient",
                    "court",
                )
            from girlframe.services.m2_state import load_state

            canon = load_state(connection, self.store.campaign_id)
            current_character = connection.scalar(
                sa.select(t.characters.c.id).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == user,
                )
            )
            for quote in canon.repair_quotes:
                if quote.owner.entity != user or quote.owner.incarnation != current_character:
                    continue
                sheet = canon.sheets.get(user)
                stale = (
                    sheet is None
                    or sheet.revision != quote.sheet_revision
                    or quote.handler != canon.handler
                    or not any(
                        x.id in quote.shortages and x.period == quote.period and not x.closed
                        for x in canon.repair_shortages
                    )
                )
                items.append(
                    InboxItem(
                        "repair-quote:" + quote.id,
                        "repair_quote",
                        quote.id,
                        quote.revision,
                        "off_duty",
                        "Extra repair price — " + quote.asset_name,
                        "Handler",
                        quote.state,
                        True,
                        stale,
                        "A price offer; no repair or spending until your explicit confirmation.",
                        "Review the private price, then accept or decline for yourself.",
                        "Review exact price" if quote.state == "pending" else None,
                        task="m3_repair_quote",
                    )
                )
            for context in canon.director_contexts:
                controlled = bool(
                    canon.world
                    and any(
                        x.id in context.directors and x.controller == viewer.user_id
                        for x in canon.world.npcs
                    )
                )
                if not context.active or (context.handler != viewer.user_id and not controlled):
                    continue
                items.append(
                    InboxItem(
                        "director-context:" + context.id,
                        "director_context",
                        context.id,
                        context.revision,
                        "world",
                        "Handler: Girl rules"
                        if context.handler == viewer.user_id
                        else "Director: current presence",
                        "Your rule context"
                        if context.handler == viewer.user_id
                        else "Your Director role",
                        "pending",
                        controlled,
                        False,
                        "Preserve the actual context until the Directors leave.",
                        "Each controller records only their own Director's actual departure.",
                        "Review current context",
                        task="m3_director_context",
                    )
                )
            if canon.world is not None:
                for offer in canon.world.npc_role_offers:
                    if viewer.user_id not in (offer.proposer, offer.npc.controller, canon.handler):
                        continue
                    incoming = viewer.user_id == offer.npc.controller
                    items.append(
                        InboxItem(
                            "npc-role:" + offer.id,
                            "npc_role",
                            offer.id,
                            canon.revision,
                            "world",
                            "NPC role invitation",
                            label(offer.proposer if incoming else offer.npc.controller),
                            offer.state,
                            incoming,
                            False,
                            "Accept to play this NPC. Scene confirmation stays separate.",
                            "Review the role privately, then give your own response.",
                            "Review NPC role" if offer.state == "pending" else None,
                            task="m3_npc_role",
                        )
                    )
            table = t.m2["m2_choices"]
            for play_row in connection.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.actor_id == user,
                    table.c.state == "pending",
                )
            ).mappings():
                if play_row["kind"] in ("dive_call", "dive_handler_void"):
                    continue
                items.append(
                    InboxItem(
                        "m2:" + play_row["id"],
                        "m2",
                        play_row["id"],
                        play_row["revision"],
                        "plays",
                        play_row["kind"].replace("_", " ").title(),
                        "Scene Play",
                        "pending",
                        True,
                        False,
                        "Resolve only your owned mechanical response.",
                        "Saved response survives restart; no timeout chooses for you.",
                        "Respond",
                        task="m2_choice",
                    )
                )
            actions = t.m2["m2_actions"]
            for saved in connection.execute(
                sa.select(actions).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.actor_id == user,
                    actions.c.state == "aborted",
                )
            ).mappings():
                body = json.loads(saved["body_json"])
                if body.get("shared_recovery") and saved["parent_id"] is None:
                    from girlframe.engine.m3_recovery_state import Interruption

                    Interruption.model_validate_json(json.dumps(body["shared_recovery"]))
                    items.append(
                        InboxItem(
                            "shared-recovery:" + saved["id"],
                            "shared-recovery",
                            saved["id"],
                            saved["revision"],
                            "plays",
                            "Recover your saved Play",
                            "Scene Play",
                            "pending",
                            True,
                            False,
                            "Resume the original response chain after staff restores chat.",
                            "Known dice, spending and prior answers stay saved. "
                            "Each player keeps their own choices.",
                            "Review recovery",
                            task="m3_shared_recovery",
                        )
                    )
                    continue
                if not body.get("actor_basic") or not body.get("actor_recovery"):
                    continue
                items.append(
                    InboxItem(
                        "actor-recovery:" + saved["id"],
                        "actor-recovery",
                        saved["id"],
                        saved["revision"],
                        "plays",
                        "Recover your actual-role Play",
                        "Scene Play",
                        "pending",
                        True,
                        False,
                        "Resume saved responses after staff restores chat.",
                        "Known dice, resource spending and human answers remain saved. "
                        "An unrolled reservation may be cancelled; "
                        "a known roll cannot be discarded.",
                        "Review recovery",
                        task="m3_actor_recovery",
                    )
                )
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_contraband import ContrabandService

            contraband = ContrabandService(GameService(self.store))
            for find in canon.contraband_finds:
                if find.actor.entity != user:
                    continue
                contraband.source(connection, find)
                items.append(
                    InboxItem(
                        "contraband:" + find.id,
                        "contraband",
                        find.id,
                        canon.revision,
                        "world",
                        "Your private contraband find",
                        find.label,
                        "pending"
                        if find.taken is None
                        else "accepted"
                        if find.taken
                        else "declined",
                        find.taken is None,
                        False,
                        "Choose whether to add this actual find as a Girl Asset.",
                        "The choice and resulting Asset stay private "
                        "until you explicitly share them.",
                        "Review your find",
                        task="m3_contraband",
                    )
                )
            for item in canon.obligations:
                if item.kind == "clone_flirt_followthrough" and item.owner == viewer.user_id:
                    items.append(
                        InboxItem(
                            "clone-followthrough:" + item.id,
                            "clone_flirt_followthrough",
                            item.id,
                            canon.revision,
                            "plays",
                            "Clone AM follow-through",
                            "Original copy owner",
                            item.state,
                            item.state == "pending",
                            False,
                            "Fulfill the actual interaction with its original partner.",
                            "The partner confirms the outcome before any Bond changes.",
                            "Review your copy",
                            task="m3_clone_am",
                        )
                    )
                if item.kind == "revoked_requisition" and viewer.user_id in (
                    item.owner,
                    item.target,
                ):
                    from girlframe.services.m3_privileges import PrivilegeService

                    privilege = PrivilegeService(self.store).view(connection, viewer, item.id)
                    items.append(
                        InboxItem(
                            "privilege:" + item.id,
                            "privilege",
                            item.id,
                            canon.revision,
                            "discipline",
                            "Temporarily revoked Requisition",
                            "Original participants",
                            "pending" if privilege["pending"] else "resolved",
                            privilege["can_allow"] or privilege["can_restore"],
                            privilege["stale"],
                            "Review the recorded restoration condition and your own decision.",
                            "Restoring an Asset preserves its original damage and Frame.",
                            "Review restoration",
                            task="m3_privilege",
                        )
                    )
                if item.kind == "tag_rejection_permission" and viewer.user_id in (
                    item.owner,
                    item.target,
                ):
                    from girlframe.services.m3_tag_permissions import PermissionService

                    permission = PermissionService(self.store)._get(connection, viewer, item.id)
                    active = permission["active"]
                    items.append(
                        InboxItem(
                            "tag-permission:" + item.id,
                            "tag_permission",
                            item.id,
                            1 if active else 2,
                            "plays",
                            "Tag rejection permission",
                            label(
                                (item.target or item.owner) if permission["owner"] else item.owner
                            ),
                            "pending" if active else "resolved",
                            active and permission["can_consent"],
                            permission["stale"],
                            "The original locker may allow rejection of this Tag.",
                            "Permission does not erase the Tag or supply "
                            "the affected player's action.",
                            "Review permission",
                            task="m3_tag_permission",
                        )
                    )
                if (
                    item.owner == viewer.user_id
                    and item.kind == "actor_reject_tag"
                    and item.state == "pending"
                ):
                    items.append(
                        InboxItem(
                            "actor-rejection:" + item.id,
                            "actor-rejection",
                            item.id,
                            canon.revision,
                            "plays",
                            "Take action to reject your Tag",
                            "Your actual Handler role",
                            "pending",
                            True,
                            False,
                            "An owned action erases the actual pending Tag.",
                            "Open in your bound scene channel. "
                            "Merely promising rejection does not erase the Tag.",
                            "Choose your owned action",
                            task="m3_actor_rejection",
                        )
                    )
            from girlframe.engine.m3_requisition_state import ComfortBenefit

            comfort_work = t.m3["m3_required_work"]
            comforts = {
                row["id"]: dict(row)
                for row in connection.execute(
                    sa.select(comfort_work)
                    .where(
                        comfort_work.c.campaign_id == self.store.campaign_id,
                        comfort_work.c.kind == "creature_comforts",
                    )
                    .order_by(comfort_work.c.revision)
                ).mappings()
            }
            for row in comforts.values():
                try:
                    benefit = ComfortBenefit.model_validate_json(
                        json.dumps(json.loads(row["body_json"])["benefit"])
                    )
                except (ValueError, KeyError):
                    raise WorkflowError(
                        "Saved Creature Comforts work needs source recovery."
                    ) from None
                owner = row["owner_id"] == user
                humans = {x.controller for x in benefit.scene.roles} if benefit.scene else set()
                if not owner and viewer.user_id not in humans:
                    continue
                answered = benefit.scene and viewer.user_id in benefit.scene.acknowledgements
                needs = row["state"] != "resolved" and (owner or not answered)
                items.append(
                    InboxItem(
                        "comforts:" + row["id"],
                        "comforts",
                        row["id"],
                        row["revision"],
                        "off_duty",
                        "Your Creature Comforts benefit"
                        if owner
                        else "Your improvement scene attendance",
                        "Owned Off-Duty opportunity",
                        "pending"
                        if needs
                        else "resolved"
                        if row["state"] == "resolved"
                        else "waiting",
                        needs,
                        False,
                        "Record only your own scene choice, attendance or Asset.",
                        "The paid source and actual qualifying roll remain saved. "
                        "Other humans supply their own attendance.",
                        "Review your next step" if needs else None,
                        task="m3_comforts" if needs else None,
                    )
                )
            from girlframe.services.m3_budget_anarchy import AnarchyService
            from girlframe.services.m3_budget_candidate import CandidateService
            from girlframe.services.m3_budget_cleanup import CleanupService
            from girlframe.services.m3_budget_director import MeetingService
            from girlframe.services.m3_budget_patron import PatronService
            from girlframe.services.m3_collective_handler_tags import CollectiveTagService
            from girlframe.services.m3_political_function import FunctionService

            for cleanup in CleanupService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "cleanup:" + cleanup["id"],
                        "budget_cleanup",
                        cleanup["id"],
                        canon.revision,
                        "off_duty",
                        "Past mission: cleanup duty",
                        "Original participants",
                        "pending" if cleanup["actionable"] else "waiting",
                        cleanup["actionable"],
                        False,
                        "Report your attendance or your selected Void alteration.",
                        "The original exposure draw is saved; "
                        "required consequences remain pending.",
                        "Review cleanup",
                        task="m3_budget_cleanup",
                    )
                )

            for anarchy in AnarchyService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "anarchy:" + anarchy["id"],
                        "budget_anarchy",
                        anarchy["id"],
                        canon.revision,
                        "world",
                        "Restore actual city order",
                        "Original Handler",
                        "available",
                        True,
                        False,
                        "Record actual civic restoration after play.",
                        "This optional restoration repairs no damage and erases no other cause.",
                        "Review city",
                        task="m3_budget_anarchy",
                    )
                )

            for candidate in CandidateService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "candidate:" + candidate["id"],
                        "budget_candidate",
                        candidate["id"],
                        canon.revision,
                        "off_duty",
                        "Pilot Candidate assessment",
                        "Original table and assigned Girl",
                        "pending",
                        True,
                        False,
                        "Define the process together, then report the actual assigned assessment.",
                        "An edited process needs new agreements; no player character is generated.",
                        "Review Candidate",
                        task="m3_budget_candidate",
                    )
                )

            for meeting in MeetingService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "director-meeting:" + meeting["id"],
                        "budget_director_meeting",
                        meeting["id"],
                        canon.revision,
                        "off_duty",
                        "Director performance meeting",
                        "Original participants",
                        "pending",
                        True,
                        False,
                        "Each human reports their own presence and choices.",
                        "The Handler uses actual Girl-rule resources in the Director's presence.",
                        "Review meeting",
                        task="m3_budget_director",
                    )
                )

            from girlframe.services.m3_budget_storage import StorageService as BudgetStorageService

            for storage_order in BudgetStorageService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "budget-storage:" + storage_order["id"],
                        "budget_storage",
                        storage_order["id"],
                        canon.revision,
                        "world",
                        "Higher-up Frame storage order",
                        "Original owner, Handler or higher-up role",
                        "pending",
                        True,
                        False,
                        "Record actual storage, refusal, warning or release.",
                        "Original bodies, Frame and source authority stay bound.",
                        "Review storage order",
                        task="m3_budget_storage",
                    )
                )

            from girlframe.services.m3_handler_pr import HandlerPRService

            for pr_control in HandlerPRService(self.store)._tasks(connection, viewer):
                pr_pending = bool(pr_control["pending"])
                items.append(
                    InboxItem(
                        "handler-pr:" + pr_control["id"],
                        "handler_pr",
                        pr_control["id"],
                        pr_control["revision"],
                        "playbook",
                        pr_control["label"],
                        "Actual host, contributor or human GM",
                        "pending" if pr_pending else "established",
                        pr_pending,
                        False,
                        "Review the performed public event and its actual result.",
                        "Award availability does not change the saved event outcome.",
                        "Review public relations",
                        task="m3_handler_pr",
                    )
                )

            from girlframe.services.m3_deep_brain_spikes import DeepBrainSpikesService

            for memory in DeepBrainSpikesService(self.store)._tasks(connection, viewer):
                pending_memory = bool(memory["pending"])
                items.append(
                    InboxItem(
                        "deep-brain-spikes:" + memory["id"],
                        "deep_brain_spikes",
                        memory["id"],
                        memory["revision"],
                        "playbook",
                        memory["label"],
                        "Original memory-scene participant",
                        "pending" if pending_memory else "established",
                        pending_memory,
                        False,
                        "Play the memory scene or review its original return.",
                        "Remembered fiction never rewinds current campaign resources.",
                        "Open memory scene",
                        task="m3_deep_brain_spikes",
                    )
                )

            from girlframe.services.m3_handler_conversion import HandlerConversionService

            for conversion in HandlerConversionService(self.store)._tasks(connection, viewer):
                pending_conversion = bool(conversion["pending"])
                items.append(
                    InboxItem(
                        "handler-conversion:" + conversion["id"],
                        "handler_conversion",
                        conversion["id"],
                        conversion["revision"],
                        "playbook",
                        conversion["label"],
                        "Original participant in this repossession",
                        "pending" if pending_conversion else "established",
                        pending_conversion,
                        False,
                        "Review actual capture, treatment and Mockingbird activation.",
                        "Private choices remain scoped to the original participants.",
                        "Review repossession",
                        task="m3_handler_conversion",
                    )
                )

            from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService

            for ordinary_control in HandlerOrdinaryService(self.store)._tasks(connection, viewer):
                ordinary_pending = bool(ordinary_control["pending"])
                items.append(
                    InboxItem(
                        "handler-ordinary:" + ordinary_control["id"],
                        "handler_ordinary",
                        ordinary_control["id"],
                        ordinary_control["revision"],
                        "playbook",
                        ordinary_control["label"],
                        "Original session or review participant",
                        "pending" if ordinary_pending else "established",
                        ordinary_pending,
                        False,
                        "Review your session or source-proved advancement choice.",
                        "Disclosure is scoped; a session record alone grants no award.",
                        "Review ordinary advancement",
                        task="m3_handler_ordinary",
                    )
                )

            from girlframe.services.m3_location_build import LocationBuildService

            for build_control in LocationBuildService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "location-build:" + build_control["id"],
                        "location_build",
                        build_control["id"],
                        build_control["revision"],
                        "playbook",
                        build_control["label"],
                        "Actual original Handler",
                        "established",
                        False,
                        False,
                        "Review the new Location and consumed advancement.",
                        "Building preserves old sites, bodies, territory and source history.",
                        "Review construction",
                        task="m3_location_build",
                    )
                )

            from girlframe.services.m3_location_rebuild import LocationRebuildService

            for rebuild_control in LocationRebuildService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "location-rebuild:" + rebuild_control["id"],
                        "location_rebuild",
                        rebuild_control["id"],
                        rebuild_control["revision"],
                        "playbook",
                        rebuild_control["label"],
                        "Actual original Handler",
                        "established",
                        False,
                        False,
                        "Review the actual rebuilt Location and consumed advancement.",
                        "Rebuilding preserves living blockers and original destruction history.",
                        "Review rebuild",
                        task="m3_location_rebuild",
                    )
                )

            from girlframe.services.m3_girl_insurance import GirlInsuranceService

            for insurance_control in GirlInsuranceService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "girl-insurance:" + insurance_control["id"],
                        "girl_insurance",
                        insurance_control["id"],
                        insurance_control["revision"],
                        "playbook",
                        insurance_control["label"],
                        "Actual original Handler",
                        "established",
                        False,
                        False,
                        "Review the acquired insurance and its actual death/Budget effect.",
                        "Automatic source effects create no acknowledgment debt.",
                        "Review insurance",
                        task="m3_girl_insurance",
                    )
                )

            from girlframe.services.m3_cute_uniforms import CuteUniformService

            for uniform_control in CuteUniformService(self.store)._tasks(connection, viewer):
                needs_confirmation = uniform_control["phase"] == "proposed"
                items.append(
                    InboxItem(
                        "cute-uniform:" + uniform_control["id"],
                        "cute_uniform",
                        uniform_control["id"],
                        uniform_control["revision"],
                        "playbook",
                        uniform_control["label"],
                        "Actual original participants",
                        "pending" if needs_confirmation else "established",
                        needs_confirmation,
                        False,
                        "Confirm only an actual dressing or review your actual clothing control.",
                        "An unperformed proposal or silence is not dressing or Tag rejection.",
                        "Review uniform",
                        task="m3_cute_uniforms",
                    )
                )

            from girlframe.services.m3_budget_removal import RemovalService

            for removal in RemovalService(self.store)._tasks(connection, viewer):
                if removal.get("actor") is None and removal.get("phase") != "complete":
                    continue  # Original Handler already has the actual parent source below.
                pending_removal = removal.get("pending", removal.get("phase") != "complete")
                items.append(
                    InboxItem(
                        "budget-removal:" + removal["id"],
                        "budget_removal",
                        removal["id"],
                        removal["revision"],
                        "playbook",
                        removal["label"],
                        "Original affected player",
                        "pending" if pending_removal else "resolved",
                        bool(pending_removal),
                        False,
                        "Choose your own actual Girl and Frame Assets or review your saved pair.",
                        "Any required loss consequences must finish before this source closes.",
                        "Review your Asset removal",
                        task="m3_budget_removal",
                    )
                )

            from girlframe.services.m3_supply_drop import SupplyDropService

            for delivery in SupplyDropService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "supply-drop:" + delivery["id"],
                        "supply_drop",
                        delivery["id"],
                        delivery["revision"],
                        "missions",
                        "Supply Drop expiry"
                        if delivery["phase"] == "expired"
                        else delivery["label"],
                        "Actual recipient and Handler",
                        "pending",
                        True,
                        False,
                        "Review your delivery or remaining expiry response.",
                        "Your delivery and any required response remain saved.",
                        "Review Supply Drop",
                        task="m3_supply_drop",
                    )
                )

            from girlframe.services.m3_handler_advancements import HandlerAdvancementService

            for award in HandlerAdvancementService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "handler-advancement:" + award["id"],
                        "handler_advancement",
                        award["id"],
                        award["revision"],
                        "playbook",
                        award["label"],
                        "Original Handler",
                        "pending",
                        True,
                        False,
                        "Spend this actual source-bound award once on a supported advancement.",
                        "Other advancement choices remain required separate implementations.",
                        "Review held advancement",
                        task="m3_handler_advancements",
                    )
                )

            from girlframe.services.m3_succubus import SuccubusService

            for request in SuccubusService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "succubus:" + request["id"],
                        "succubus_npc_order",
                        request["id"],
                        request["revision"],
                        "playbook",
                        request["label"],
                        "Original response owner",
                        "pending",
                        True,
                        False,
                        "Respond for the actual NPC role.",
                        "No controller Pilot resources substitute for this recipient.",
                        "Review original Order",
                        task="m3_succubus",
                    )
                )

            from girlframe.services.m3_special_girl import SpecialGirlService

            for request in SpecialGirlService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "special-girl:" + request["id"],
                        "special_girl_token",
                        request["id"],
                        canon.revision,
                        "playbook",
                        "Handler's Special Girl token",
                        "Original Handler or token recipient",
                        "pending" if request["actionable"] else "waiting",
                        request["actionable"],
                        False,
                        "The Handler names the actual token; its owner chooses a legal Asset slot.",
                        "Original source and exact authored Asset remain bound.",
                        "Review token",
                        task="m3_special_girl",
                    )
                )

            from girlframe.services.m3_rebel_leader import LeaderService

            for opportunity in LeaderService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "rebel-leader:" + opportunity["id"],
                        "rebel_leader",
                        opportunity["id"],
                        canon.revision,
                        "world",
                        "Rebel leader opportunity",
                        "Original Handler",
                        "pending" if opportunity["phase"] == "available" else "resolved",
                        opportunity["phase"] == "available",
                        False,
                        "The leader's death can enable group destruction; this is optional.",
                        "The actual source remains bound; no personal kill credit is inferred.",
                        "Review opportunity",
                        task="m3_rebel_leader",
                    )
                )

            from girlframe.services.m3_void_retirement import StipendService

            for stipend_offer in StipendService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "void-retirement:" + stipend_offer["id"],
                        "void_retirement",
                        stipend_offer["id"],
                        canon.revision,
                        "world",
                        "Retirement with stipend",
                        "Affected player",
                        "pending" if stipend_offer["phase"] == "offered" else "resolved",
                        stipend_offer["phase"] == "offered",
                        False,
                        "Your original Girl owns acceptance or refusal.",
                        "Acceptance ends this career with a saved archive and stipend.",
                        "Review private offer",
                        task="m3_void_retirement",
                    )
                )

            from girlframe.services.m3_rebel_contact import ContactService

            for contact in ContactService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "contact:" + contact["id"],
                        "rebel_contact",
                        contact["id"],
                        canon.revision,
                        "off_duty",
                        "Your private regular NPC contact",
                        "Original Girl or actual NPC role",
                        "resolved"
                        if contact["phase"] == "complete"
                        else "pending"
                        if contact["actionable"]
                        else "waiting",
                        contact["actionable"],
                        False,
                        "Describe only your own actual repeatable contact or NPC response.",
                        "The connection is private to these actual source roles.",
                        "View contact" if contact["phase"] == "complete" else "Review contact",
                        task="m3_rebel_contact",
                    )
                )

            from girlframe.services.m3_budget_fight import FightService

            for fight in FightService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "fight:" + fight["id"],
                        "budget_fight",
                        fight["id"],
                        canon.revision,
                        "off_duty",
                        "Televised fight",
                        "Two original Girls and source Handler",
                        "pending",
                        True,
                        False,
                        "Confirm only your actual participation or the real fight ending.",
                        "Combat declarations and consequences use the actual Play scene.",
                        "Review fight",
                        task="m3_budget_fight",
                    )
                )

            from girlframe.services.m3_budget_assassination import AssassinationService

            for assignment in AssassinationService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "assassination:" + assignment["id"],
                        "budget_assassination",
                        assignment["id"],
                        canon.revision,
                        "mission",
                        "Political assassination assignment",
                        "Original Handler and genuine mission",
                        "pending",
                        True,
                        False,
                        "Offer or review the actual source-bound assassination mission.",
                        "Players own acceptance; success requires actual target death.",
                        "Review assignment",
                        task="m3_budget_assassination",
                    )
                )

            from girlframe.services.m3_budget_visitor import VisitorService

            for visit in VisitorService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "visit:" + visit["id"],
                        "budget_visitor",
                        visit["id"],
                        canon.revision,
                        "off_duty",
                        "Higher-up visit and reparations",
                        "Original NPC controller or affected Girl",
                        "pending",
                        True,
                        False,
                        "Record actual demands or your own performed response.",
                        "No automated charge or forced player dialogue.",
                        "Review visit",
                        task="m3_budget_visitor",
                    )
                )

            for activity in FunctionService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "function:" + activity["id"],
                        "political_function",
                        activity["id"],
                        canon.revision,
                        "off_duty",
                        "Political function: " + activity["kind"],
                        "Original function participants",
                        "pending",
                        True,
                        False,
                        "Read your Tag rights and confirm only actual attendance or actions.",
                        "No player action or dialogue is generated.",
                        "Review function",
                        task="m3_political_function",
                    )
                )

            for patron in PatronService(self.store).available(connection, viewer):
                items.append(
                    InboxItem(
                        "patron:" + patron["id"],
                        "budget_patron",
                        patron["id"],
                        canon.revision,
                        "playbook",
                        "Report a real patron visit",
                        patron["patron"],
                        "available",
                        True,
                        False,
                        "The patron takes an interest in " + patron["girl"] + ".",
                        "Only actual witnessed evidence grants a Handler Tag.",
                        "Report visit",
                        task="m3_budget_patron",
                    )
                )

            for tag_task in CollectiveTagService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "collective-tag:" + tag_task["id"],
                        "collective_handler_tag",
                        tag_task["id"],
                        tag_task["revision"],
                        "off_duty",
                        tag_task["title"],
                        "Original Girls",
                        "pending" if tag_task["actionable"] else "resolved",
                        tag_task["actionable"],
                        False,
                        "Each original Girl supplies her own exact-label agreement.",
                        "An unused optional opportunity does not block Off-Duty. "
                        "An actual proposal waits for its human decisions.",
                        "Review collective Tag" if tag_task["actionable"] else None,
                        task="m3_collective_tag",
                    )
                )
            from girlframe.services.m3_alpha_sex import SexService
            from girlframe.services.m3_am_scrutinized import ScrutinyService
            from girlframe.services.m3_janus_play import BatteryService

            for source in ScrutinyService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "am-source:" + source["id"],
                        "am_source",
                        source["id"],
                        source["revision"],
                        "plays",
                        source["label"],
                        "Original source scene",
                        "pending" if source["actionable"] else "waiting",
                        source["actionable"],
                        False,
                        "Give your own response to this original discovery or Limiter source.",
                        "The original scene and its human roles remain bound.",
                        "Review AM source",
                        task="m3_am_source",
                    )
                )
            from girlframe.services.m3_am_body import BodyService

            for body_swap in BodyService(GameService(self.store))._tasks(connection, viewer):
                pending_body = bool(body_swap["pending"])
                items.append(
                    InboxItem(
                        "am-body:" + body_swap["id"],
                        "am_body",
                        body_swap["id"],
                        body_swap["revision"],
                        "playbook",
                        body_swap["label"],
                        "Original AM or actual circuit operator",
                        "pending" if pending_body else "established",
                        pending_body,
                        False,
                        "Review actual body hardware or return while genuinely connected.",
                        "Same mind and current resources; both bodies retain actual conditions.",
                        "Review AM bodies",
                        task="m3_am_body",
                    )
                )

            from girlframe.services.m3_am_code import CodeService

            for maintenance in CodeService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "am-code:" + maintenance["id"],
                        "am_code_source",
                        maintenance["id"],
                        canon.revision,
                        "plays",
                        "AM circuit maintenance",
                        "Original AM and actual operator",
                        "pending" if maintenance["actionable"] else "waiting",
                        maintenance["actionable"],
                        False,
                        "Give your own response to this circuit maintenance source.",
                        "The original person, operator and actual scene remain bound.",
                        "Review AM maintenance",
                        task="m3_am_code_source",
                    )
                )

            from girlframe.services.m3_physiotherapist import PhysiotherapistService

            for therapy in PhysiotherapistService(GameService(self.store))._tasks(
                connection, viewer
            ):
                items.append(
                    InboxItem(
                        "physiotherapist:" + therapy["id"],
                        "physiotherapist",
                        therapy["id"],
                        canon.revision,
                        "off_duty",
                        "Void Physiotherapist",
                        "Original patient and NPC controller",
                        "pending" if therapy["actionable"] else "waiting",
                        therapy["actionable"],
                        False,
                        "Review your actual relationship or therapy scene.",
                        "Only the original participants supply their responses.",
                        "Review physiotherapist",
                        task="m3_physiotherapist",
                    )
                )

            from girlframe.services.m3_martyr import MartyrService

            for memorial in MartyrService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "martyr:" + memorial["id"],
                        "martyr_memorial",
                        memorial["id"],
                        memorial["revision"],
                        "playbook",
                        "Choose your character's memorial",
                        "Your original character",
                        "pending",
                        memorial["actionable"],
                        False,
                        "Choose how your original character is remembered.",
                        "This preserves its death and belongs to its original human.",
                        "Choose memorial",
                        task="m3_martyr",
                    )
                )

            for invitation in SexService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "alpha-consent:" + invitation["id"],
                        "alpha_sex_consent",
                        invitation["id"],
                        invitation["revision"],
                        "plays",
                        invitation["label"],
                        "Original participants only",
                        "pending",
                        invitation["actionable"],
                        False,
                        "Read the actual proposal and give your own voluntary answer.",
                        "No roll or Heat is spent before your confirmation.",
                        "Review invitation",
                        task="m3_alpha_consent",
                    )
                )

            for mind in BatteryService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "janus-mind:" + mind["id"],
                        "janus_brain_link",
                        mind["id"],
                        mind["revision"],
                        "plays",
                        "Your private brain link",
                        "Only the two actual linked minds",
                        "pending",
                        mind["actionable"],
                        False,
                        "Read or send your own private direct brain communication.",
                        "This actual link must remain connected; no speech or public transcript.",
                        "Open private brain link",
                        task="m3_janus_mind",
                    )
                )
            from girlframe.services.m3_doctor_care import CareService
            from girlframe.services.m3_doctor_procedures import ProcedureService
            from girlframe.services.m3_janus import JanusService
            from girlframe.services.m3_janus_pet import PetService
            from girlframe.services.m3_janus_storage import StorageService

            for doctor_source, doctor_task in (
                (CareService(GameService(self.store)), "m3_doctor_care"),
                (ProcedureService(GameService(self.store)), "m3_doctor_procedure"),
            ):
                for doctor_request in doctor_source._tasks(connection, viewer):
                    items.append(
                        InboxItem(
                            doctor_task + ":" + doctor_request["id"],
                            "doctor_request",
                            doctor_request["id"],
                            doctor_request["revision"],
                            "plays",
                            "Actual DoctorDoctor request",
                            "Original provider and patient",
                            "pending",
                            doctor_request["actionable"],
                            False,
                            "Review your own actual source-bound care or procedure.",
                            "No response, movement or repair is invented.",
                            "Open actual request",
                            task=doctor_task,
                        )
                    )

            storage_tasks = StorageService(GameService(self.store))._tasks(connection, viewer)
            for stored_surgery in storage_tasks:
                items.append(
                    InboxItem(
                        "janus-storage:" + stored_surgery["id"],
                        "janus_void_surgery",
                        stored_surgery["id"],
                        stored_surgery["revision"],
                        "off_duty",
                        "Actual stored Void surgical request",
                        "Original patient and Foundation",
                        "pending",
                        stored_surgery["actionable"],
                        False,
                        "The Foundation records one actual surgical removal in this period.",
                        "No permanent Void or Asset damage is undone.",
                        "Review actual surgery",
                        task="m3_janus_storage",
                    )
                )

            for outing in PetService(GameService(self.store))._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "janus-pet:" + outing["id"],
                        "janus_pet_outing",
                        outing["id"],
                        outing["revision"],
                        "off_duty",
                        "Actual Core outing and return",
                        "Original Pilot and Foundation",
                        outing["phase"],
                        outing["actionable"],
                        False,
                        "Choose actual Core care or return her to the original Frame.",
                        "No automatic transport or invented Tag is supplied.",
                        "Review actual Core care",
                        task="m3_janus_pet",
                    )
                )

            for core_task in JanusService(GameService(self.store))._tasks(connection, viewer):
                pending_core = core_task["phase"] in ("controller", "review")
                items.append(
                    InboxItem(
                        "janus-core:" + core_task["id"],
                        "janus_core_setup",
                        core_task["id"],
                        core_task["revision"],
                        "playbook",
                        "Original JANUS Core setup",
                        "Original Pilot, Core controller and Foundation source judge",
                        "pending"
                        if core_task["actionable"]
                        else "waiting"
                        if pending_core
                        else "resolved",
                        core_task["actionable"],
                        False,
                        "A distinct unnamed original Core shares the existing JANUS Frame.",
                        "The actual controller supplies factual resources. "
                        "The Foundation reviews them. "
                        "No other PC, former history or paid ability is copied.",
                        "Review actual setup",
                        task="m3_janus_core",
                    )
                )
            from girlframe.services.m3_physical import PhysicalService

            physical = PhysicalService(self.store)
            from girlframe.services.m3_battle import BattleService
            from girlframe.services.m3_battle_dormant import DormantService
            from girlframe.services.m3_careers import CareerService
            from girlframe.services.m3_handler_creation import HandlerCreationService
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService
            from girlframe.services.m3_harpy_physical import HarpyPhysicalService

            harpy_service = HarpyDefeatService(self.store)
            for harpy_task in harpy_service._tasks(connection, viewer):
                if (
                    harpy_task["kind"] == "harpy_defeat"
                    and harpy_task.get("action")
                    and any(
                        choice["actor_id"] == str(viewer.user_id)
                        for choice in harpy_service.game.pending(connection, harpy_task["action"])
                    )
                ):
                    continue
                items.append(
                    InboxItem(
                        "harpy-task:" + harpy_task["kind"] + ":" + harpy_task["id"],
                        harpy_task["kind"],
                        harpy_task["id"],
                        canon.revision,
                        "plays",
                        harpy_task["label"],
                        "Original Harpy and actual source participants",
                        "pending",
                        harpy_task["can_act"],
                        False,
                        "Continue only the actual source-owned response for this original role.",
                        "Saved dice and physical facts remain tied to the original person.",
                        "Review actual next step",
                        task="m3_harpy_task:" + harpy_task["kind"],
                    )
                )
            for harpy_physical in HarpyPhysicalService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "harpy-physical:" + harpy_physical["id"],
                        "harpy_physical",
                        harpy_physical["id"],
                        harpy_physical["revision"],
                        "plays",
                        "Review actual Harpy help"
                        if harpy_physical["review"]
                        else "Actual Harpy Frame and body",
                        "Original Frame voice and actual source-scene helpers",
                        "pending",
                        harpy_physical["actionable"],
                        False,
                        "Frame consent, extraction and medical recovery each require a real act.",
                        "Only physical flags change; no resources or transport are inferred.",
                        "Review actual help"
                        if harpy_physical["review"]
                        else "Review physical controls",
                        task="m3_harpy_help" if harpy_physical["review"] else "m3_harpy_physical",
                    )
                )
            for dormant in DormantService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "dormant:" + dormant["id"],
                        "dormant",
                        dormant["id"],
                        dormant["revision"],
                        "plays",
                        "Dormant: actual Void and required Dive",
                        "Original affected person",
                        dormant["state"],
                        dormant["actionable"],
                        False,
                        "The source remains held through actual corruption and required Dive.",
                        "Resume the actual owned consequence; a new character cannot substitute.",
                        "Review Dormant consequence",
                        task="m3_dormant",
                    )
                )
            from girlframe.services.m3_handler_void import HandlerVoidService
            from girlframe.services.m3_mockingbird_plays import MockingbirdService

            for handler_void in (
                HandlerVoidService(self.store)._tasks(connection, viewer)
                if canon.handler_void
                else ()
            ):
                items.append(
                    InboxItem(
                        "handler-void:" + handler_void["id"],
                        "handler_void",
                        handler_void["id"],
                        canon.revision,
                        "plays",
                        handler_void["label"],
                        "Actual original Handler body",
                        handler_void["state"],
                        handler_void["can_act"],
                        False,
                        "Choose actual removal or stabilization; later treatment stays saved.",
                        "A successor body cannot answer for the original Handler.",
                        "Review actual Handler Void",
                        task="handler_void",
                    )
                )
            from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService
            from girlframe.services.m3_sprite import SpriteService

            for girl_void in (
                HandlerGirlVoidService(self.store)._tasks(connection, viewer)
                if canon.handler_girl_void
                else ()
            ):
                items.append(
                    InboxItem(
                        "handler-girl-void:" + girl_void["id"],
                        "handler_girl_void",
                        girl_void["id"],
                        canon.revision,
                        "plays",
                        girl_void["label"],
                        "Original source body and caster",
                        girl_void["state"],
                        girl_void["can_act"],
                        False,
                        "Use only real existing Assets and your own source-owned response.",
                        "No assigned Frame, copied resources or automatic recovery is created.",
                        "Review actual Void effect",
                        task="handler_girl_void",
                    )
                )
            for sprite in SpriteService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "sprite-intercept:" + sprite["id"],
                        "sprite_intercept",
                        sprite["id"],
                        sprite["revision"],
                        "plays",
                        sprite["label"],
                        "Actual original Sprite controller",
                        sprite["state"],
                        sprite["incoming"],
                        False,
                        "Choose your own real Sprite to intercept this actual blow, or pass.",
                        "No role, resources, movement or dice are created for another controller.",
                        "Review interception",
                        task="sprite_intercept",
                    )
                )
            from girlframe.services.m3_quadrant_loss import LossService

            for source_task in (
                LossService(self.store)._tasks(connection, viewer)
                if any(x.get("kind") == "quadrant_loss" for x in canon.facts)
                else ()
            ):
                items.append(
                    InboxItem(
                        "quadrant-loss:" + source_task["id"],
                        "quadrant_loss",
                        source_task["id"],
                        source_task["revision"],
                        "world",
                        source_task["label"],
                        "Actual original aftermath participants",
                        "pending",
                        source_task["incoming"],
                        False,
                        "Resolve the actual source loss aftermath without inventing a new body.",
                        "Employment, replacement and transport remain separate actual owned steps.",
                        "Review actual aftermath",
                        task="quadrant_loss",
                    )
                )
            for mock_task in MockingbirdService(physical.game)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "mockingbird:" + mock_task["id"],
                        mock_task["kind"],
                        mock_task["id"],
                        canon.revision,
                        "plays",
                        "Mockingbird: " + mock_task["kind"].replace("mockingbird_", ""),
                        "Actual original participants",
                        mock_task["state"],
                        mock_task["actionable"],
                        False,
                        "Review only your original role's trigger or conversation permission.",
                        "Actual conversations use only their selected capabilities; "
                        "no out-of-character explanation.",
                        "Review actual source",
                        task="m3_mockingbird",
                    )
                )
            if any(x.get("kind") == "gorgon_dormant_stage" for x in canon.facts):
                from girlframe.services.m3_gorgon_dormant import GorgonDormantService

                for debt in GorgonDormantService(self.store)._tasks(connection, viewer):
                    items.append(
                        InboxItem(
                            "gorgon-dormant:" + debt["id"],
                            "gorgon_dormant_void",
                            debt["id"],
                            debt["revision"],
                            "plays",
                            debt["label"],
                            "Your actual original Gorgon",
                            debt["state"],
                            debt["incoming"],
                            False,
                            "Resolve the real source Dormant counter-Void without a proxy body.",
                            "The debt remains accessible when its original Play is interrupted.",
                            "Review actual Dormant consequence",
                            task="gorgon_dormant_void",
                        )
                    )
            from girlframe.services.m3_mockingbird_discovery import DiscoveryService
            from girlframe.services.m3_mockingbird_revision import SexRevisionService

            discovery_tasks = (
                DiscoveryService(physical.game)._tasks(connection, viewer)
                if canon.mockingbird.exposures or canon.mockingbird.discoveries
                else []
            )
            revision_tasks = SexRevisionService(physical.game)._tasks(connection, viewer)
            from girlframe.services.m3_mockingbird_communion import CallService

            call_tasks = (
                [
                    dict(x, kind="mockingbird_call")
                    for x in CallService(physical.game)._tasks(connection, viewer)
                ]
                if canon.mockingbird.calls
                else []
            )
            from girlframe.services.m3_passengers import PassengerService

            passenger_tasks = (
                [
                    dict(x, kind="call_passenger")
                    for x in PassengerService(physical.game)._tasks(connection, viewer)
                ]
                if canon.passengers
                else []
            )
            for source_task in (*discovery_tasks, *revision_tasks, *call_tasks, *passenger_tasks):
                items.append(
                    InboxItem(
                        source_task["kind"] + ":" + source_task["id"],
                        source_task["kind"],
                        source_task["id"],
                        canon.revision,
                        "plays",
                        "Actual Call communion"
                        if source_task["kind"] == "mockingbird_call"
                        else "Actual discovery"
                        if source_task["kind"] != "mockingbird_sex_revision"
                        else "Revise uncommitted resources",
                        "Your original source-owned role",
                        source_task["state"],
                        source_task["actionable"],
                        False,
                        "Review actual source facts and only your own choices.",
                        "Private backend knowledge does not establish discovery, "
                        "consent or a new resource.",
                        "Review actual source",
                        task=source_task["kind"],
                    )
                )
            if canon.world is not None and any(
                "leviathan" in body.types for body in canon.world.gorgons
            ):
                from girlframe.services.m3_leviathan import LeviathanService

                for layer_play in LeviathanService(self.store)._tasks(connection, viewer):
                    items.append(
                        InboxItem(
                            "leviathan-layers:" + layer_play["id"],
                            "leviathan_layers",
                            layer_play["id"],
                            layer_play["revision"],
                            "plays",
                            "Protect " + layer_play["label"] + " with flesh layers",
                            "Your actual original Leviathan",
                            "available",
                            True,
                            False,
                            "Raise two actual flesh-layer Assets around this Core.",
                            "Original guards and weakness remain; existing damage cannot reset.",
                            "Describe actual layers",
                            task="leviathan_layers",
                        )
                    )
            for battle_context in BattleService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "battle-context:" + battle_context["id"],
                        "battle_context",
                        battle_context["id"],
                        battle_context["revision"],
                        "plays",
                        battle_context["label"],
                        "Actual declarer and human adjudicator",
                        "pending",
                        battle_context["state"] == "confirmed" or battle_context["incoming"],
                        False,
                        "Review the actual original bodies, owned Assets, opening and reach.",
                        "Stage: "
                        + battle_context["state"]
                        + ". No dice or movement is supplied by this review.",
                        "Review combat declaration",
                        task="m3_battle_context",
                    )
                )
            from girlframe.services.m3_handler_plays import HandlerPlayService
            from girlframe.services.m3_medical import MedicalService
            from girlframe.services.m3_privacy_trouble import PrivacyTroubleService
            from girlframe.services.m3_scene_requisitions import SceneRequisitionService

            for request in HandlerPlayService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "handler-play:" + request["id"],
                        "handler_play",
                        request["id"],
                        canon.revision,
                        "plays",
                        request["label"],
                        "Your actual source-owned choice",
                        "pending",
                        request["can_act"],
                        False,
                        "Choose only the actual Handler Play granted by this source.",
                        "No player answer, consent, body or resource is invented "
                        "by opening this request.",
                        "Review Handler Play",
                        task="m3_handler_play",
                    )
                )
            for notice in HandlerPlayService(self.store)._notices(connection, viewer):
                items.append(
                    InboxItem(
                        "handler-notice:" + notice["id"],
                        "handler_notice",
                        notice["id"],
                        canon.revision,
                        "plays",
                        notice["label"],
                        "Actual source information for you",
                        "resolved",
                        False,
                        False,
                        "Read the actual committed Handler Play affecting your original character.",
                        "Actual effect stage: " + notice["state"] + ". "
                        "This notice supplies no answer or consent; "
                        "mechanical follow-ups remain separate.",
                        "Read actual Handler notice",
                        task="m3_handler_notice",
                    )
                )
            from girlframe.services.m3_handler_tags import HandlerTagService

            for notice in HandlerTagService(GameService(self.store)).notices(connection, viewer):
                items.append(
                    InboxItem(
                        "handler-tag-notice:" + notice["id"],
                        "handler_tag_notice",
                        notice["id"],
                        notice["revision"],
                        "plays",
                        "A Girl requests your undivided attention",
                        "Your original Handler role",
                        "resolved" if notice["read"] else "pending",
                        True,
                        False,
                        "Read the actual private request made by spending your observed Tag.",
                        "Reading records only receipt of this notice; "
                        "it creates no fictional answer, dialogue or resource.",
                        "Read the attention request",
                        task="handler_tag_notice",
                    )
                )
            for request in HandlerCreationService(self.store)._tasks(
                connection, viewer, history=True
            ):
                items.append(
                    InboxItem(
                        "handler-creation:" + request["id"],
                        "handler_creation",
                        request["id"],
                        request["revision"],
                        "playbook",
                        request["label"],
                        "Original shared participants",
                        "pending" if request["actionable"] else request["state"],
                        request["actionable"],
                        request["stale"],
                        "Review only your own exact creation choices or shared agreement.",
                        "Private Handler details stay with their original creator.",
                        "Review creation",
                        task=request["kind"],
                    )
                )
            for request in SceneRequisitionService(physical.game)._scene_tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "scene-requisition:" + request["id"],
                        "scene_requisition",
                        request["id"],
                        request["revision"],
                        "off_duty",
                        request["kind"].replace("_", " ").title(),
                        label(request["buyer"]),
                        request["state"],
                        request["state"] != "resolved",
                        False,
                        "Review your actual paid scene and your own participation.",
                        "Other participants supply only their own responses.",
                        "Review scene",
                        task="m3_scene_requisition",
                    )
                )
            for request in PrivacyTroubleService(self.store)._trouble_tasks(connection, viewer):
                actionable = (
                    request["own"] and request["state"] != "resolved" and not request["stale"]
                )
                items.append(
                    InboxItem(
                        "privacy-trouble:" + request["id"],
                        "privacy_trouble",
                        request["id"],
                        request["revision"],
                        "off_duty",
                        "Privacy incident inquiry",
                        "Original participants",
                        request["state"],
                        actionable,
                        request["stale"],
                        "Review the actual inquiry and choose only your response.",
                        "Private-room secrets are never disclosed automatically.",
                        "Review inquiry",
                        task="m3_privacy_trouble",
                    )
                )
            for request in MedicalService(self.store)._tasks(connection, viewer, history=True):
                items.append(
                    InboxItem(
                        "medical:" + request["id"],
                        "medical",
                        request["id"],
                        request["revision"],
                        "plays",
                        request["label"],
                        "Original patient and care reviewer",
                        request["state"],
                        request["actionable"],
                        request["stale"],
                        "Record actual care, waking and your owned Play exchange.",
                        "Waking does not repair Assets or restore a different character.",
                        "Review recovery",
                        task="m3_medical",
                    )
                )
            from girlframe.services.m3_girl_transition import GirlTransitionService
            from girlframe.services.m3_standards import StandardsService

            for service, workflow_task in (
                (GirlTransitionService(self.store), "m3_girl_transition"),
                (StandardsService(self.store), "m3_standards"),
            ):
                for request in service._tasks(connection, viewer, history=True):
                    items.append(
                        InboxItem(
                            workflow_task + ":" + request["id"],
                            workflow_task,
                            request["id"],
                            request["revision"],
                            "playbook",
                            request["label"],
                            "Original character and assigned choosers",
                            request["state"],
                            request["actionable"],
                            request["stale"],
                            "Complete your own original character's saved choices.",
                            "Each participant supplies only their assigned details.",
                            "Review choices",
                            task=workflow_task,
                        )
                    )
            from girlframe.services.m3_enforcer import EnforcerService
            from girlframe.services.m3_frame_swap import FrameSwapService
            from girlframe.services.m3_handler_consequences import HandlerConsequenceService
            from girlframe.services.m3_lobotomy import LobotomyService
            from girlframe.services.m3_personal_firearm import PersonalFirearmService
            from girlframe.services.m3_void import VoidService

            for request in HandlerConsequenceService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "handler-consequence:" + request["id"],
                        "handler_consequence",
                        request["id"],
                        canon.revision,
                        "plays",
                        "Your actual Handler body consequence",
                        "Your original body",
                        "pending",
                        True,
                        False,
                        "Choose only your own actual source consequence.",
                        "Persistent injury, an actual opening or original-body death "
                        "is recorded explicitly.",
                        "Review Handler consequence",
                        task="m3_handler_consequence",
                    )
                )
            for request in VoidService(self.store)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "void:" + request["id"],
                        "void",
                        request["id"],
                        request["revision"],
                        "plays",
                        request["title"],
                        "Original Girl and actual source participants",
                        "pending",
                        True,
                        False,
                        "Resolve the actual source Void state; "
                        "a text acknowledgment cannot complete it.",
                        "Stage: "
                        + request["state"]
                        + ". The source Play remains held until its real consequences finish.",
                        "Review Void",
                        task="m3_void",
                    )
                )
            surgery_service = LobotomyService(self.store)
            surgery_tasks = {x["id"]: x for x in surgery_service._tasks(connection, viewer)}
            visible_surgeries = set()
            for surgery in canon.lobotomies:
                if user not in (surgery.subject.entity, surgery.inflictor.entity):
                    continue
                visible_surgeries.add(surgery.id)
                actionable = surgery.id in surgery_tasks
                items.append(
                    InboxItem(
                        "surgery:" + surgery.id,
                        "surgery",
                        surgery.id,
                        canon.revision,
                        "missions",
                        "Original-patient surgery",
                        "Original patient and inflictor",
                        "resolved" if surgery.phase == "applied" else "pending",
                        actionable,
                        False,
                        "The inflictor owns the exact effects; "
                        "the original patient owns each description.",
                        "Stage: "
                        + surgery.phase
                        + ". No answer or surgery effect is supplied automatically.",
                        "Review surgery",
                        task="m3_lobotomy",
                    )
                )
            from girlframe.services.m3_role_punishments import RolePunishmentService

            role_cases = RolePunishmentService(physical.game)._tasks(connection, viewer)
            visible_role_work = {
                case.pc_work
                for case in canon.role_punishments
                if case.id in {x["id"] for x in role_cases} and case.pc_work is not None
            }
            for request in role_cases:
                items.append(
                    InboxItem(
                        "role-punishment:" + request["id"],
                        "role_punishment",
                        request["id"],
                        canon.revision,
                        "plays",
                        "Original instruction and actual Punishment",
                        "Original chooser, executor and affected participant",
                        request["state"],
                        request["actionable"],
                        False,
                        "Each human owns only their actual instruction, "
                        "consultation, scene or execution.",
                        "The source Play waits for the real instructed effects "
                        "and their required follow-ups.",
                        "Review actual Punishment",
                        task="m3_role_punishment",
                    )
                )
            for request in FrameSwapService(physical.game)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "frame-swap:" + request["id"],
                        "frame_swap",
                        request["id"],
                        request["revision"],
                        "off_duty",
                        "Optional paid Frame Swap",
                        "Original buyer and assigned recipient",
                        "resolved" if request["state"] == "resolved" else "pending",
                        request["state"] != "resolved",
                        False,
                        "Review the actual saved plan and your own source-bound response.",
                        "Saving a plan never charges Permissions; "
                        "a complete confirmed exchange does.",
                        "Review Frame Swap",
                        task="m3_frame_swap",
                    )
                )
            for request in PersonalFirearmService(physical.game)._return_tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "firearm-return:" + request["id"],
                        "firearm_return",
                        request["id"],
                        request["revision"],
                        "off_duty",
                        "Retrieve lost Personal Firearm",
                        "Original entitled Girl",
                        "resolved" if request["state"] == "resolved" else "pending",
                        request["state"] != "resolved",
                        False,
                        "Only a real earned lost-pistol return can issue the actual item.",
                        "Review the original entitlement and explicitly accept or decline; "
                        "no Permission charge.",
                        "Review firearm return",
                        task="m3_firearm_return",
                    )
                )
            from girlframe.services.m3_enforcer_volunteer import VolunteerService

            for request in VolunteerService(physical.game)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "enforcer-volunteer:" + request["id"],
                        "enforcer_volunteer",
                        request["id"],
                        request["revision"],
                        "plays",
                        "Actual Enforcer volunteering offer",
                        "Original inflictor and proposed executor",
                        request["state"],
                        request["state"] == "pending" and request["actionable"],
                        False,
                        "The original chooser accepts or declines this exact actual executor.",
                        "The original Punishment cause and chooser remain unchanged; "
                        "real effects still follow.",
                        "Review volunteer offer",
                        task="m3_enforcer_volunteer",
                    )
                )
            from girlframe.services.m3_items import ItemService

            for request in ItemService(physical.game)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "held-item-fact:" + request["id"],
                        "held_item_fact",
                        request["id"],
                        request["revision"],
                        "world",
                        "Actual existing held object",
                        "Original holder and human GM",
                        request["state"],
                        request["state"] == "pending" and request["actionable"],
                        False,
                        "Confirm only an actual existing possession, not a new mechanical Asset.",
                        "The actual human GM reviews the source holder "
                        "and whether the object is a weapon on hand.",
                        "Review factual possession",
                        task="m3_item_fact",
                    )
                )
            for request in EnforcerService(physical.game)._grasp_tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "enforcer-grasp:" + request["id"],
                        "enforcer_grasp",
                        request["id"],
                        request["revision"],
                        "plays",
                        "Your actual held grasp",
                        "Original holder",
                        request["state"],
                        request["actionable"],
                        False,
                        "Release only the actual source-owned grip.",
                        "Voluntary release moves nobody and does not remove separate Helplessness.",
                        "Review voluntary release" if request["actionable"] else None,
                        task="m3_enforcer_grasp" if request["actionable"] else None,
                    )
                )
            for request in EnforcerService(physical.game)._tasks(connection, viewer):
                items.append(
                    InboxItem(
                        "enforcer:" + request["id"],
                        "enforcer",
                        request["id"],
                        request["revision"],
                        "world",
                        request["kind"].replace("_", " ").title(),
                        "Original Enforcer and current Handler",
                        "resolved" if request["state"] == "resolved" else "pending",
                        request["state"] != "resolved" and viewer.user_id == canon.handler,
                        False,
                        "Actual rank, innocence evidence or release position stays source-bound.",
                        "The Handler records factual evidence; "
                        "no innocence, guilt or map location is invented.",
                        "Review Enforcer case",
                        task="m3_enforcer",
                    )
                )
            if any(fact.get("kind") == "compliance_virus_past_link" for fact in canon.facts):
                from girlframe.services.m3_virus_exposure import ExposureService

                for request in ExposureService(physical.game)._tasks(connection, viewer):
                    items.append(
                        InboxItem(
                            "virus-exposure:" + request["id"],
                            "virus_exposure",
                            request["id"],
                            canon.revision,
                            "plays",
                            "Actual past link exposure",
                            "Original factual source roles",
                            "pending",
                            request["can_act"],
                            False,
                            "Only actual original linker, Frame owner and frozen judge "
                            "own this source.",
                            "No current control, Frame assignment or location is granted.",
                            "Review exposure",
                            task="m3_virus_exposure",
                        )
                    )
            careers = CareerService(self.store)
            for archive in canon.career_archives:
                if archive.actor.entity != user:
                    continue
                _, proved = careers._archive(connection, viewer, archive.id)
                items.append(
                    InboxItem(
                        "career:" + proved.id,
                        "career",
                        proved.id,
                        canon.revision,
                        "playbook",
                        "Your original character archive",
                        "Your ended career",
                        "resolved",
                        False,
                        False,
                        "Read the preserved original sheet and history.",
                        "A replacement starts a separate actual character.",
                        "Review archive",
                        task="m3_career",
                    )
                )
            if canon.handler == viewer.user_id:
                for request in careers._return_candidates(connection, viewer):
                    items.append(
                        InboxItem(
                            "career-return-offer:" + request["id"],
                            "career_return_offer",
                            request["id"],
                            request["game_revision"],
                            "playbook",
                            "Offer an original character's return",
                            request["callsign"],
                            "pending",
                            True,
                            False,
                            "The original player chooses whether to resume this character.",
                            "Choose an explicit return Status and describe the actual release.",
                            "Offer return",
                            task="m3_career_return_offer",
                        )
                    )
                for request in careers._status_requests(connection, viewer):
                    if request["position"] is not None:
                        continue
                    items.append(
                        InboxItem(
                            "career-status:" + request["character"],
                            "career_status",
                            request["character"],
                            request["game_revision"],
                            "playbook",
                            "Assign new-character starting Status",
                            request["callsign"],
                            "pending",
                            True,
                            False,
                            "Choose the new original character's actual starting position.",
                            "The prior character's rank is not inherited.",
                            "Assign Status",
                            task="m3_career_status",
                            target=request["owner"],
                        )
                    )
            for request in careers._return_requests(connection, viewer):
                items.append(
                    InboxItem(
                        "career-return:" + request["id"],
                        "career_return",
                        request["id"],
                        canon.revision,
                        "playbook",
                        "Original character return offer",
                        "Handler",
                        "pending",
                        True,
                        False,
                        "Choose whether to resume your actual archived original character.",
                        "Resources and conditions stay preserved; "
                        "an active replacement is reserved.",
                        "Review return",
                        task="m3_career_return",
                    )
                )
            for lock in canon.frame_locks:
                try:
                    request = physical._frame(connection, viewer, lock.id)
                except WorkflowError:
                    continue
                items.append(
                    InboxItem(
                        "frame-physical:" + lock.id,
                        "frame_physical",
                        lock.id,
                        request["revision"],
                        "world",
                        "Frame consent and extraction",
                        request["label"],
                        "pending" if lock.active else "resolved",
                        lock.active and (request["can_voice"] or bool(request["extractors"])),
                        False,
                        "Review actual Frame consent, opening and physical extraction.",
                        "Extraction alone grants no healing or restored vital signs.",
                        "Review Frame",
                        task="m3_frame_physical",
                    )
                )
            approval = self.store.policy.m3_approval
            if (
                approval is not None
                and "world" in approval.subsystems
                and canon.world is not None
                and user in canon.sheets
            ):
                from girlframe.engine.m3_actor_state import ActorRef

                try:
                    initial_ref = ActorRef(
                        kind="pilot",
                        entity=user,
                        incarnation=physical.game.character_binding(
                            connection, canon, viewer.user_id, require_current_profile=False
                        ),
                    )
                except WorkflowError:
                    initial_ref = None
                if (
                    initial_ref is not None
                    and not any(x.actor == initial_ref for x in canon.placements)
                    and not any(
                        physical._review(connection, row).proposal.actor == initial_ref
                        for row in physical._rows(connection)
                        if row["state"] == "pending"
                    )
                ):
                    initial_identity = initial_ref.incarnation
                    assert initial_identity is not None
                    items.append(
                        InboxItem(
                            "physical-initial:" + initial_identity,
                            "physical_initial_task",
                            initial_identity,
                            canon.sheets[user].revision,
                            "world",
                            "Record original physical facts",
                            canon.sheets[user].callsign,
                            "pending",
                            True,
                            False,
                            "Your actual body and Frame positions are not recorded yet.",
                            "Propose your actual first map positions and occupancy "
                            "for facilitator review.",
                            "Record physical facts",
                            task="m3_physical_start",
                        )
                    )

            for request in physical._tasks(connection, viewer, history=True):
                pending = request["state"] != "resolved"
                items.append(
                    InboxItem(
                        "physical:" + request["id"],
                        "physical_setup",
                        request["id"],
                        request["revision"],
                        "world",
                        "Original physical facts",
                        request["label"],
                        "pending" if pending else "resolved",
                        pending and request["incoming"],
                        False,
                        "An owned factual proposal for the original Girl and Frame.",
                        "Review actual map positions and occupancy; "
                        "the facilitator confirms the original facts.",
                        "Review physical facts" if pending else "View physical facts",
                        task="m3_physical",
                    )
                )

            from girlframe.engine.m3_missions import Mission

            current_handler = handler.current(connection)[1].handler_id
            table = t.m3["m3_missions"]
            for mission_body in connection.scalars(
                sa.select(table.c.body_json).where(table.c.campaign_id == self.store.campaign_id)
            ):
                mission = Mission.model_validate_json(mission_body)
                if viewer.user_id not in mission.offered_to and viewer.user_id != current_handler:
                    continue
                needs_response = (
                    mission.phase == "offered"
                    and viewer.user_id in mission.offered_to
                    and user not in mission.responses
                )
                handler_action = viewer.user_id == current_handler and mission.phase in (
                    "offered",
                    "active",
                    "ending",
                    "awaiting_consequences",
                )
                items.append(
                    InboxItem(
                        "mission:" + mission.id,
                        "mission",
                        mission.id,
                        mission.revision,
                        "missions",
                        "Mission offer" if mission.phase == "offered" else "Mission progress",
                        "Handler",
                        "pending"
                        if mission.phase not in ("complete", "cancelled")
                        else mission.phase,
                        needs_response or handler_action,
                        False,
                        (
                            "Only your own acceptance/decline is recorded. "
                            "Required effects cannot be skipped."
                        ),
                        mission.objective,
                        "Review mission",
                        task="m3_mission",
                    )
                )
            from girlframe.engine.m3_off_duty import Period, Progress

            table = t.m3["m3_off_duty"]
            for body in connection.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.phase == "active"
                )
            ):
                period = Period.model_validate_json(body)
                invited = (
                    period.handler_scene and viewer.user_id in period.handler_scene.participants
                )
                invited = invited or any(
                    progress.scene and viewer.user_id in progress.scene.participants
                    for progress in period.progress.values()
                )
                if (
                    viewer.user_id not in period.pilots
                    and viewer.user_id != current_handler
                    and not invited
                ):
                    continue

                def period_task(
                    suffix: str, title: str, counterpart: str, period: Period = period
                ) -> None:
                    items.append(
                        InboxItem(
                            "off-duty:" + period.id + ":" + suffix,
                            "off_duty",
                            period.id,
                            period.revision,
                            "off_duty",
                            title,
                            counterpart,
                            "pending",
                            True,
                            False,
                            "Your own saved Off-Duty decision remains pending.",
                            "Reopen the period to review current legal choices. "
                            "Each participant confirms their own scene; no timer answers for them.",
                            "Review Off-Duty",
                            task="m3_off_duty",
                        )
                    )

                if viewer.user_id in period.pilots:
                    own_progress = period.progress.get(user, Progress())
                    if not own_progress.recovered:
                        title = (
                            "Go Off-Duty / resume your saved Play"
                            if own_progress.roll is None
                            else "Finish Off-Duty Tag decisions"
                            if own_progress.roll.stage == "tag_window"
                            else "Choose your Off-Duty scene"
                            if own_progress.scene is None and not own_progress.scene_declined
                            else "Complete your Off-Duty recovery"
                        )
                        period_task("own", title, "Your sheet")
                for owner, off_duty_progress in period.progress.items():
                    scene = off_duty_progress.scene
                    if (
                        scene is not None
                        and viewer.user_id in scene.participants
                        and viewer.user_id not in scene.acknowledgements
                    ):
                        period_task(
                            "scene:" + owner,
                            "Confirm your Off-Duty scene participation",
                            label(owner),
                        )
                scene = period.handler_scene
                if (
                    scene is not None
                    and viewer.user_id in scene.participants
                    and viewer.user_id not in scene.acknowledgements
                ):
                    period_task(
                        "handler-scene", "Confirm your Handler scene participation", "Handler"
                    )
                if viewer.user_id == current_handler and period.status_review is not None:
                    period_task("end", "Review world effects and end Off-Duty", "Cadre")
            table = t.m3["m3_required_work"]
            latest_work = {
                row["id"]: dict(row)
                for row in connection.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        sa.or_(table.c.owner_id == user, table.c.subject_id == user),
                    )
                    .order_by(table.c.revision)
                ).mappings()
            }
            for work in latest_work.values():
                if work["state"] == "resolved":
                    continue
                primary, task_name = None, None
                kind = work["kind"]
                if kind in (
                    "creature_comforts",
                    "physical_initial",
                    "janus_core_setup",
                    "handler_creation",
                    "handler_creation_agreement",
                    "handler_creation_npc_agreement",
                    "scene_requisition",
                    "privacy_trouble",
                    "privacy_inquiry_response",
                    "defeat_medical_wake",
                    "girl_playbook_transition",
                    "girl_standards",
                    "void_threshold",
                    "defeat_void_threshold",
                    "frame_swap",
                    "personal_firearm_return",
                    "enforcer_rank",
                    "held_item_fact",
                    "enforcer_volunteer",
                    "dormant_void",
                    "harpy_physical_help",
                    "harpy_defeat",
                    "quadrant_loss",
                    "compliance_virus_purge",
                    "mockingbird_handler_void",
                    "mockingbird_handler_girl_void",
                    "mockingbird_redirect_handler_void",
                    "mockingbird_redirect_handler_girl_void",
                    "dive_handler_void",
                    "call_guest_handler_girl_void",
                    "sprite_intercept",
                    "gorgon_dormant_void",
                ):
                    continue
                if work["id"] in visible_role_work:
                    continue
                if json.loads(work["body_json"]).get("lobotomy_id") in visible_surgeries:
                    continue
                context_scene = (
                    json.loads(work["body_json"]).get("context_scene")
                    if kind == "punishment"
                    else None
                )
                scene_attestation = bool(
                    context_scene
                    and viewer.user_id in context_scene["participants"]
                    and viewer.user_id not in context_scene["acknowledgements"]
                )
                if kind in (
                    "punishment",
                    "punishment_consult",
                    "punishment_paired_identity_heat",
                    "punishment_helpless",
                    "punishment_frame_loss",
                ):
                    primary, task_name = "Review discipline", "m3_discipline"
                elif kind == "handler_tag_response":
                    primary, task_name = "Reply to Handler Tag", "handler_tag_response"
                elif kind == "defeat":
                    primary, task_name = "Resolve actual Defeat", "m3_defeat"
                elif kind in (
                    "doctor_frame_replacement",
                    "defeat_frame_replacement_active",
                    "frame_replacement_package",
                    "frame_replacement_court",
                ):
                    primary, task_name = "Review replacement", "m3_replacement"
                elif kind in ("doctor_obsolescence", "princess_mission_end"):
                    primary, task_name = "Review reaction", "m3_reaction"
                elif kind in ("off_duty_strain_start", "strain_roll", "strain_endgame"):
                    primary, task_name = "Review Strain", "m3_strain"
                elif kind == "doctor_credit":
                    primary, task_name = "Record credit sharing", "m3_off_duty_credit"
                elif kind in ("observation_choice", "observation_effect"):
                    primary, task_name = "Review Observation", "m3_observation"
                elif kind == "director_presence":
                    primary, task_name = "Review actual presence", "m3_director_review"
                elif kind in (
                    "frame_off_duty_reward",
                    "frame_reward_court",
                    "frame_reward_interest",
                ):
                    primary, task_name = "Review Frame bonus", "m3_frame_reward"
                elif kind in ("off_duty_handler_scene", "off_duty_status_review"):
                    primary, task_name = "Review Off-Duty", "m3_off_duty"
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.budget.endgame.6"
                ):
                    primary, task_name = "Review collective Handler Tags", "m3_collective_tag"
                elif kind == "collective_handler_tag_vote":
                    continue  # Canonical proposal projection above retains this actual vote source.
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.budget.endgame.3"
                ):
                    primary, task_name = "Choose two ruined locations", "m3_budget_ruin"
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.rebellion.endgame.2"
                ):
                    primary, task_name = "Resolve actual group merger", "m3_rebel_merge"
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.rebellion.endgame.1"
                ):
                    primary, task_name = "Identify actual leader opportunity", "m3_rebel_leader"
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.void.endgame.4"
                ):
                    primary, task_name = "Offer retirement with stipend", "m3_void_retirement"
                elif kind == "strain_endgame_effect" and json.loads(work["body_json"]).get(
                    "rule_id"
                ) in ("strain.void.endgame.6", "strain.void.endgame.7"):
                    primary, task_name = (
                        "Claim actual Handler advancement",
                        "m3_handler_advancements",
                    )
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.budget.endgame.7"
                ):
                    primary, task_name = "Resolve actual NPC departures", "m3_budget_departures"
                elif (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.budget.endgame.4"
                ):
                    primary, task_name = "Review actual player Asset removals", "m3_budget_removal"
                elif kind == "budget_handler_tag" or (
                    kind == "strain_endgame_effect"
                    and json.loads(work["body_json"]).get("rule_id") == "strain.budget.endgame.5"
                ):
                    primary, task_name = "Review persistent Handler Tag", "m3_budget_tag"
                elif kind == "strain_event":
                    from girlframe.engine.m3_strain_effects import SUPPORTED

                    if json.loads(work["body_json"])["rule_id"] in SUPPORTED:
                        primary, task_name = "Apply Strain consequences", "m3_strain_effect"
                title = {
                    "punishment": "Required Punishment",
                    "handler_tag_response": "Reply to Handler Tag",
                    "doctor_frame_replacement": "Choose replacement Frame",
                    "defeat_frame_replacement_active": "Choose replacement for lost Frame",
                    "defeat_frame_replacement": "Destroyed Frame: replacement next Off-Duty",
                    "frame_replacement_package": "Package awaiting confirmation"
                    if work["state"] == "quoted"
                    else "Define replacement package",
                    "frame_replacement_court": "Confirm replacement Court role",
                    "off_duty_strain_start": "Strain start review and required effects",
                    "strain_roll": "Saved Strain roll / event choice",
                    "strain_endgame": "Choose an unused Strain Endgame",
                    "strain_event": "Required Strain event effects",
                    "strain_endgame_effect": "Required Endgame effects",
                    "budget_handler_tag": "Name your persistent Handler Tag",
                    "doctor_credit": "DoctorDoctor credit sharing",
                    "observation_choice": "Your Void Observation consequences",
                    "observation_effect": "Required Observation details",
                    "director_presence": "Director presence: Handler rule context",
                    "frame_off_duty_reward": "Frame Off-Duty Permission review",
                    "frame_reward_court": "Resolve actual Queen AM holder",
                    "frame_reward_interest": "Does this offering interest you?",
                    "off_duty_handler_scene": "Required Handler Off-Duty scene",
                    "off_duty_status_review": "End-of-Off-Duty Status review",
                }.get(
                    kind,
                    "Required Off-Duty work"
                    if work["off_duty_id"]
                    else "Required mission reaction"
                    if work["mission_id"]
                    else "Required scene work"
                    if work.get("scene_id")
                    else "Required campaign work",
                )
                items.append(
                    InboxItem(
                        "mission-work:" + work["id"],
                        "mission_work",
                        work["id"],
                        work["revision"],
                        "off_duty"
                        if work["off_duty_id"]
                        else "missions"
                        if work["mission_id"]
                        else "plays"
                        if work.get("scene_id")
                        else "world",
                        title,
                        label(work["subject_id"]),
                        "pending",
                        (
                            (work["owner_id"] == user and work["state"] != "awaiting_interest")
                            or scene_attestation
                        )
                        and not (kind == "frame_replacement_package" and work["state"] == "quoted"),
                        False,
                        "A required consequence remains pending.",
                        (
                            "Resolve this with the designated participant; "
                            "an offline player or timer cannot waive it."
                        ),
                        primary,
                        task=task_name,
                    )
                )
        return tuple(
            sorted(
                items,
                key=lambda x: (
                    x.state != "pending",
                    not (x.incoming or x.stale),
                    -datetime.fromisoformat(x.sort_time).timestamp() if x.sort_time else 0,
                    x.key,
                ),
            )
        )

    def page(
        self,
        viewer: GuildViewer,
        scope: str = "pending",
        category: str = "all",
        index: int = 0,
        *,
        selected_key: str | None = None,
        expected_revision: int | None = None,
    ) -> InboxPage:
        if scope not in SCOPES or category not in CATEGORIES:
            raise WorkflowError("Unknown inbox filter.")
        items = [x for x in self.items(viewer) if category == "all" or x.category == category]

        def matches(x: InboxItem, value: str) -> bool:
            return (
                x.state != "pending"
                if value == "history"
                else x.state == "pending"
                and (value == "pending" or (x.incoming or x.stale) == (value == "you"))
            )

        counts = {key: sum(matches(x, key) for x in items) for key in SCOPES}
        filtered = [x for x in items if matches(x, scope)]
        position = min(max(index, 0), max(len(filtered) - 1, 0))
        if selected_key is not None:
            found = next((i for i, x in enumerate(filtered) if x.key == selected_key), None)
            if found is None or (
                expected_revision is not None and filtered[found].revision != expected_revision
            ):
                raise WorkflowError("This request changed. Refresh and select its current version.")
            position = found
        start = (position // 5) * 5
        return InboxPage(
            filtered[position] if filtered else None,
            position,
            len(filtered),
            counts,
            tuple(filtered[start : start + 5]),
        )

    def current(self, viewer: GuildViewer, key: str, revision: int) -> InboxItem:
        item = next((x for x in self.items(viewer) if x.key == key), None)
        if item is None or item.revision != revision:
            raise WorkflowError("This request changed. Refresh the inbox; saved data is preserved.")
        return item

    def decide(
        self, viewer: GuildViewer, interaction: str, item: InboxItem, decision: Decision
    ) -> None:
        # Existing services own idempotency, revision and authority checks. Delegating
        # the original snapshot lets an exact interaction retry return its receipt.
        if item.key != item.source + ":" + item.identity:
            raise WorkflowError("This request identifier is invalid.")
        if item.source == "bond":
            self.bonds.decide(viewer, interaction, item.identity, item.revision, decision)
        elif item.source == "shared":
            self.shared.decide(viewer, interaction, item.identity, item.revision, decision)
        elif item.source == "coordination":
            self.coordination.decide(viewer, interaction, item.identity, item.revision, decision)
        else:
            raise WorkflowError("Open the task's authorized wizard instead.")
