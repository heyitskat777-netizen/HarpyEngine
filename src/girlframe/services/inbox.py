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
                ):
                    primary, task_name = "Review discipline", "m3_discipline"
                elif kind in (
                    "doctor_frame_replacement",
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
                elif kind == "strain_event":
                    from girlframe.engine.m3_strain_effects import SUPPORTED

                    if json.loads(work["body_json"])["rule_id"] in SUPPORTED:
                        primary, task_name = "Apply Strain consequences", "m3_strain_effect"
                title = {
                    "punishment": "Required Punishment",
                    "doctor_frame_replacement": "Choose replacement Frame",
                    "frame_replacement_package": "Package awaiting confirmation"
                    if work["state"] == "quoted"
                    else "Define replacement package",
                    "frame_replacement_court": "Confirm replacement Court role",
                    "off_duty_strain_start": "Strain start review and required effects",
                    "strain_roll": "Saved Strain roll / event choice",
                    "strain_endgame": "Choose an unused Strain Endgame",
                    "strain_event": "Required Strain event effects",
                    "strain_endgame_effect": "Required Endgame effects",
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
                    else "Required mission reaction",
                )
                items.append(
                    InboxItem(
                        "mission-work:" + work["id"],
                        "mission_work",
                        work["id"],
                        work["revision"],
                        "off_duty" if work["off_duty_id"] else "missions",
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
