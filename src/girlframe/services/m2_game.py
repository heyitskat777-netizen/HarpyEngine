"""Transactional M2 canonical state, activation, scenes and durable Play actions."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import (
    PLAY_IDS,
    RULESET,
    AssetState,
    ChoiceAnswer,
    GameState,
    IdentityState,
    Obligation,
    PilotSheet,
    PlayInput,
    higher,
    mark_identity,
    pair_key,
    spend_heat,
)
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_plays import ASSET_IDS as M3_ASSET_IDS
from girlframe.engine.m3_plays import FIXED_IDS as M3_FIXED_IDS
from girlframe.engine.m3_plays import HEAT_IDS as M3_HEAT_IDS
from girlframe.engine.m3_plays import JANUS_ROLL_IDS
from girlframe.engine.m3_plays import ROLL_IDS as M3_ROLL_IDS
from girlframe.engine.m3_policy import RULESET as M3_RULESET
from girlframe.engine.rolls import DiceSource, OsDice
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state, public_sheet
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

PUBLIC_FIELDS = {
    "frame_name",
    "appearance",
    "frame_appearance",
    "identities",
    "assets",
    "asset_descriptions",
}


class GameService:
    def __init__(self, store: OnboardingStore, *, dice: DiceSource | None = None):
        self.store = store
        self.dice = dice if dice is not None else OsDice()
        self.rng_source = "os" if dice is None else "test_injected"

    def gate(self) -> None:
        approval = self.store.policy.m2_approval
        if (
            approval is None
            or approval.registry_sha256 != registry_digest()
            or self.store.policy.owner_intense_tag_bonus is None
        ):
            raise WorkflowError("M2_REVIEW_PENDING: gameplay awaits the end-of-M2 release review.")

    def authorize(self, c: Connection, viewer: GuildViewer, *, game: bool = True) -> None:
        self.store.guild_member(viewer)
        self.store._membership(c, viewer)
        if game:
            self.gate()
            if self.director_mode_pending(c, viewer.user_id):
                raise WorkflowError(
                    "UNSUPPORTED_RULE: resolve the Director's Handler/Girl rules context first."
                )
            state = load_state(c, self.store.campaign_id)
            if (
                state.sheets
                and HandlerService(self.store).current(c)[1].handler_id != state.handler
            ):
                raise WorkflowError("STALE_HANDLER: canonical Handler replacement needs review.")

    def unpaused(self, c: Connection) -> None:
        if c.execute(
            sa.select(t.pauses).where(t.pauses.c.campaign_id == self.store.campaign_id)
        ).first():
            raise WorkflowError(
                "SAFETY_PAUSED: gameplay is paused; recovery and saved views remain available."
            )

    def event(
        self,
        c: Connection,
        actor: int | str,
        key: str,
        kind: str,
        state: GameState | None = None,
        *,
        event_id: str | None = None,
        event_index: int = 0,
        **metadata: Any,
    ) -> str:
        if state is not None:
            from girlframe.services.m3_incarnations import prepare_write

            bound, binding_proof = prepare_write(c, self.store.campaign_id, state)
            for field in GameState.model_fields:
                setattr(state, field, getattr(bound, field))
            if binding_proof:
                metadata["legacy_identity_bindings"] = binding_proof
            from girlframe.engine.m3_consume import (
                InternalCustody,
                MouthHold,
            )
            from girlframe.engine.m3_consume import (
                records as consume_records,
            )

            if (
                any(x.frame == "CONSUME" for x in state.sheets.values())
                or bool(consume_records(state, InternalCustody))
                or bool(consume_records(state, MouthHold))
            ):
                from girlframe.services.p1_consume_hooks import before_write as consume_transitions

                event_id = event_id or str(uuid4())
                consume_transitions(
                    self, c, load_state(c, self.store.campaign_id), state, event_id, metadata
                )
            from girlframe.engine import m3_wyvern as wyvern_rules

            if any(
                wyvern_rules.records(state, model)
                for model in (wyvern_rules.Last, wyvern_rules.Pin, wyvern_rules.Shield)
            ):
                from girlframe.services.m3_wyvern import stage_unlink
                from girlframe.services.m3_wyvern_combat import observe

                event_id = event_id or str(uuid4())
                before = load_state(c, self.store.campaign_id)
                from girlframe.services.m3_wyvern_support import guard_damage_changes

                guard_damage_changes(self, c, before, state)
                for last in wyvern_rules.records(state, wyvern_rules.Last):
                    if not last.unlinked_event:
                        stage_unlink(self, c, before, state, last.actor, event_id)
                observe(self, c, before, state, event_id)
            state.revision += 1
            metadata["game_revision"] = state.revision
        if kind.startswith("m3.") and self.store.policy.m3_approval is not None:
            metadata["rules_registry_sha256"] = self.store.policy.m3_approval.registry_sha256
        event = self.store._audit(
            c,
            actor,
            key,
            kind,
            metadata,
            event_id=event_id,
            event_index=event_index,
            ruleset_version=M3_RULESET if kind.startswith("m3.") else RULESET,
        )
        if state is not None:
            if any(x.get("kind") == "learned_hound_status_use" for x in state.facts):
                from girlframe.engine.m3_learned_play_state import stamp_hound_clears

                stamp_hound_clears(state, event)
            from girlframe.engine.m3_careers import stamp_tag_givers
            from girlframe.engine.m3_enforcer import end_lost_frame_grasps

            if any(grip.held and grip.contact == "frame" for grip in state.enforcer_grasps):
                released = end_lost_frame_grasps(state, event)
                state.enforcer_grasps = released.enforcer_grasps

            principal = None
            ooc_tags = [tag for sheet in state.sheets.values() for tag in sheet.tags]
            ooc_tags.extend(state.handler_tags)
            if any(tag.gm_setter_appointment is not None for tag in ooc_tags):
                from girlframe.services.m3_medical import MedicalService

                try:
                    human, appointment = MedicalService(self.store)._handler(c)
                except WorkflowError:
                    pass
                else:
                    if str(actor) == str(human):
                        principal = (human, appointment)
            previous_state = load_state(c, self.store.campaign_id)
            if any(x.get("kind") == "a_bomb_drop" for x in (*previous_state.facts, *state.facts)):
                from girlframe.services.m3_a_bomb import prepare_ejections

                prepare_ejections(self, c, previous_state, state, event)
            if any(x.frame == "DOCTORDOCTOR MK. II" for x in previous_state.sheets.values()):
                from girlframe.services.m3_doctor_lifecycle import prepare as doctor_lifecycle

                doctor_lifecycle(self, c, previous_state, state, event)
            if any(
                getattr(x, "rule_id", None) == "frame.class.autocrat.martyr"
                for x in previous_state.requisitions
            ):
                from girlframe.services.m3_martyr import prepare as prepare_martyr

                prepare_martyr(self, c, previous_state, state, event)
            if any(
                fact.get("kind") == "girl_insurance_acquisition" for fact in previous_state.facts
            ):
                from girlframe.services.m3_girl_insurance import prepare as prepare_insurance

                prepare_insurance(self, c, previous_state, state, event)
            if state.neural_connections:
                from girlframe.engine.m3_frame_control import prepare_endings as end_neural_sources

                neural_state = end_neural_sources(previous_state, state, event)
                for field in GameState.model_fields:
                    setattr(state, field, getattr(neural_state, field))
            from girlframe.engine.m3_janus_storage import end_inactive_causes

            end_inactive_causes(state, event)
            for fact in state.facts:
                if fact.get("kind") == "blocked_by_obsession" and not fact.get("event"):
                    fact["event"] = event
            if any(fact.get("kind") == "compliance_virus_frame" for fact in state.facts):
                from girlframe.services.m3_compliance_virus import (
                    prepare_endings,
                    prepare_transmission,
                )

                transmitted = prepare_transmission(self, c, previous_state, state, event)
                transmitted = prepare_endings(previous_state, transmitted, event)
                state.facts = transmitted.facts
                state.role_punishments = transmitted.role_punishments
            from girlframe.services.m3_handler_plays import verified_tag_grants

            actor_text = str(actor)
            human_actor = (
                int(actor_text)
                if len(actor_text) <= 20 and actor_text.isascii() and actor_text.isdecimal()
                else None
            )
            if human_actor is not None and (
                not 0 < human_actor < 2**64 or str(human_actor) != actor_text
            ):
                human_actor = None
            scoped_principals = verified_tag_grants(
                c, self, previous_state, state, actor=human_actor, event=event, kind=kind
            )
            bound = stamp_tag_givers(
                previous_state,
                state,
                event,
                gm_principal=principal,
                gm_grants=scoped_principals,
            )
            for field in GameState.model_fields:
                setattr(state, field, getattr(bound, field))
            from girlframe.engine.m3_red_queen import JUDGEMENT as COURT_JUDGEMENT

            if any(getattr(x, "rule_id", None) == COURT_JUDGEMENT for x in state.requisitions):
                from girlframe.services.m3_red_queen_support import stage_tag_births

                stage_tag_births(self, c, previous_state, state, event)
            if self.store.policy.m3_approval is not None:
                from girlframe.engine.m3_actor_state import ActorRef as BirthActor
                from girlframe.engine.m3_girl_runtime_state import has_rule as birth_rule
                from girlframe.services.m3_malleable import stage_birth

                def qualify(giver: BirthActor, recipient: BirthActor, tag_id: str) -> None:
                    source_sheet = previous_state.sheets.get(giver.entity)
                    if (
                        giver.kind == "pilot"
                        and source_sheet is not None
                        and source_sheet.character_id == giver.incarnation
                        and birth_rule(
                            source_sheet,
                            "girl.stim-blissed.malleable-me-malleable-you",
                            "STIM-BLISSED",
                        )
                    ):
                        stage_birth(self, c, previous_state, state, giver, recipient, tag_id, event)

                for sheet in state.sheets.values():
                    if not sheet.character_id:
                        continue
                    previous = previous_state.sheets.get(str(sheet.owner))
                    if previous is None or previous.character_id != sheet.character_id:
                        continue  # A new person cannot have a prior altered-state source here.
                    old_ids = {tag.id for tag in previous.tags}
                    recipient = BirthActor(
                        kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id
                    )
                    for tag in sheet.tags:
                        if tag.id not in old_ids and tag.giver_actor is not None:
                            qualify(tag.giver_actor, recipient, tag.id)
                if state.world is not None:
                    old_npcs = (
                        {npc.id: npc for npc in previous_state.world.npcs}
                        if previous_state.world
                        else {}
                    )
                    for npc in state.world.npcs:
                        if npc.id not in old_npcs:
                            continue
                        old_ids = {tag.id for tag in old_npcs[npc.id].tags}
                        for world_tag in npc.tags:
                            if world_tag.id in old_ids:
                                continue
                            try:
                                giver = BirthActor.model_validate_json(world_tag.giver_entity)
                            except ValueError:
                                continue  # Older non-character setters grant no new ability.
                            qualify(giver, BirthActor(kind="npc", entity=npc.id), world_tag.id)
            if any(
                fact.get("kind") == "tracker_acquisition"
                for fact in (*previous_state.facts, *state.facts)
            ):
                from girlframe.services.m3_tracker_implants import prepare as prepare_trackers

                prepare_trackers(self, c, previous_state, state, event)
            if any(sheet.frame == "PROJECT ANKOU" for sheet in state.sheets.values()) or any(
                fact.get("kind", "").startswith("ankou_")
                and not fact.get("kind", "").startswith("ankou_feedback")
                for fact in state.facts
            ):
                from girlframe.services.m3_ankou import observe as observe_ankou

                observe_ankou(
                    self, c, previous_state, state, event, metadata | dict(event_kind=kind)
                )
            from girlframe.services.m3_changeling_hooks import stage as stage_changeling

            stage_changeling(self, c, previous_state, state, event, metadata)
            from girlframe.services.m3_intracadre_marriage import prepare_punishments

            prepare_punishments(self, c, previous_state, state, event)
            body = GameState.model_validate_json(state.model_dump_json()).model_dump_json()
            c.execute(
                t.m2["m2_state_history"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    revision=state.revision,
                    body_json=body,
                    event_id=event,
                )
            )
            table = t.m2["m2_state"]
            where = table.c.campaign_id == self.store.campaign_id
            if c.execute(sa.select(table.c.revision).where(where)).first():
                c.execute(
                    table.update().where(where).values(revision=state.revision, body_json=body)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, revision=state.revision, body_json=body
                    )
                )
        if state is not None and self.store.policy.m3_approval is not None:
            from girlframe.services.m3_debts import synchronize

            synchronize(c, self.store, state, event)
            if any(x.get("kind") == "doctor_track_mark" for x in state.facts):
                from girlframe.services.m3_doctor_lifecycle import (
                    synchronize as sync_doctor_lifecycle,
                )

                sync_doctor_lifecycle(self, c, state, event)
            if any(x.get("kind") == "martyr_episode" for x in state.facts):
                from girlframe.services.m3_martyr import synchronize as sync_martyr

                sync_martyr(self, c, state, event)
        if state is not None and any(
            x.get("kind") == "a_bomb_radiation" and x.get("event") == event for x in state.facts
        ):
            from girlframe.services.m3_a_bomb import synchronize_ejections

            synchronize_ejections(self, c, state, event, metadata.get("action_id"))
        if state is not None and any(
            fact.get("kind") == "compliance_virus_purge" for fact in state.facts
        ):
            from girlframe.services.m3_compliance_virus import synchronize_endings

            synchronize_endings(self, c, event)
        if state is not None and any(
            x.phase == "ended" and x.ended_event == event for x in state.neural_connections
        ):
            from girlframe.services.m3_frame_control import synchronize_endings as end_neural_work

            end_neural_work(self, c, event)
        if (
            state is not None
            and state.frame_commands
            and any(x.source_event == event for x in state.harpy_states)
        ):
            from girlframe.services.m3_frame_control import synchronize_birth_controls

            controlled_birth = synchronize_birth_controls(self, c, event)
            for field in GameState.model_fields:
                setattr(state, field, getattr(controlled_birth, field))
        if self.store.policy.m3_approval is not None:
            from girlframe.services.m3_alpha import synchronize_counters as alpha_counters

            alpha_state = alpha_counters(self, c, event)
            if state is not None and alpha_state is not None:
                for field in GameState.model_fields:
                    setattr(state, field, getattr(alpha_state, field))
        if state is not None and any(
            x.get("kind") == "janus_storage_cause_ended" and x.get("event") == event
            for x in state.facts
        ):
            from girlframe.services.m3_janus_storage import complete_stopped

            complete_stopped(self, c, state, event, None, str(uuid4()))
        if state is not None and any(x.get("kind") == "alpha_sex_session" for x in state.facts):
            from girlframe.services.m3_alpha_sex import synchronize_counters as sex_counters

            sex_state = sex_counters(self, c, event)
            if sex_state is not None:
                for field in GameState.model_fields:
                    setattr(state, field, getattr(sex_state, field))

        if state is not None and any(
            fact.get("kind", "").startswith("ankou_")
            and not fact.get("kind", "").startswith("ankou_feedback")
            for fact in state.facts
        ):
            from girlframe.services.m3_ankou import synchronize_events as sync_ankou_events

            sync_ankou_events(self, c, event)
            newest = load_state(c, self.store.campaign_id)
            if newest.revision > state.revision:
                for field in GameState.model_fields:
                    setattr(state, field, getattr(newest, field))
        if state is not None and any(x.get("kind") == "changeling_body_fact" for x in state.facts):
            from girlframe.services.m3_changeling import synchronize_brains

            synchronize_brains(self, c, event)
        if state is not None:
            from girlframe.services.p1_source_pause import reserve

            reserve(self, c, state)
        return event

    def sheet(self, viewer: GuildViewer, owner: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(owner if owner is not None else viewer.user_id))
            if sheet is None:
                raise WorkflowError("This Pilot has no activated M2 sheet.")
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.engine.m3_janus_storage import active as stored_void

            if sheet.character_id:
                points = stored_void(
                    state,
                    ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id),
                )
                if points:
                    sheet = sheet.model_copy(deep=True)
                    for asset in sheet.assets:
                        point = next((x for x in points if x.asset == asset.id), None)
                        if point is not None:
                            asset.void, asset.description = True, point.description
            data = (
                sheet.model_dump(mode="json")
                if sheet.owner == viewer.user_id
                else public_sheet(sheet, state)
            )
            from girlframe.services.m3_red_queen_accusation import official_allegations

            if sheet.character_id:
                data["official_allegations"] = official_allegations(
                    state,
                    "girl",
                    ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id),
                )
            if sheet.owner == viewer.user_id:
                from girlframe.engine.m3_clone_am import additional_identities
                from girlframe.services.m3_clone_am import prove_additional

                additional = additional_identities(state, sheet.owner)
                if additional:
                    prove_additional(self, c, state, sheet.owner)
                data["additional_identities"] = [x.model_dump(mode="json") for x in additional]
                from girlframe.engine.m3_oldgen import marked_maxims

                data["marked_maxims"] = [
                    {"id": key, "name": name, "marked": True}
                    for key, name in marked_maxims(state, sheet.owner)
                ]
            if sheet.owner == viewer.user_id and sheet.character_id:
                from girlframe.engine.m3_actor_state import ActorRef

                subject = ActorRef(
                    kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id
                )
                broken = [
                    x
                    for x in state.alpha_broken
                    if x.subject == subject and x.removed_event is None
                ]
                if broken:
                    data["broken_against"] = [x.inflictor.model_dump(mode="json") for x in broken]
                from girlframe.engine.m3_control_ritual import owned as own_rituals

                data["control_rituals"] = [
                    dict(
                        id=x.id,
                        label=x.tag.label,
                        marked=x.tag.marked,
                        rejection_pending=x.tag.rejection_pending,
                    )
                    for x in own_rituals(state, sheet.owner)
                    if x.tag
                ]
            if sheet.owner == viewer.user_id and sheet.character_id:
                from girlframe.engine import m3_am as am_rules

                am_actor = ActorRef(
                    kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id
                )
                if sheet.girl == "AM" or am_rules.limiters(state, am_actor):
                    from girlframe.engine.m3_am_backup import backups
                    from girlframe.engine.m3_am_backup import latest as latest_backup_reversion
                    from girlframe.engine.m3_am_memory import losses as memory_losses

                    reversion = latest_backup_reversion(state, am_actor)

                    data["am_runtime"] = dict(
                        backups=[
                            dict(id=x.id, captured_revision=x.captured_revision)
                            for x in backups(state, am_actor)
                        ],
                        memory_reversion=reversion.model_dump(mode="json") if reversion else None,
                        memory_erasures=[
                            dict(
                                scope=x.scope,
                                memories=list(x.memories),
                                through_revision=x.through_revision,
                                event=x.event,
                            )
                            for x in memory_losses(state, am_actor)
                        ],
                        presentation=am_rules.presentation(state, am_actor),
                        limited=[
                            dict(identity=x.identity, slot=x.slot, freedom=x.freedom)
                            for x in am_rules.limiters(state, am_actor)
                        ],
                    )
            if sheet.owner == viewer.user_id and sheet.character_id:
                from girlframe.engine.m3_actor_bonds import current_ref as prince_sheet_ref
                from girlframe.engine.m3_prince import official_pronouns

                pronouns = official_pronouns(state, prince_sheet_ref(state, sheet.owner))
                if pronouns:
                    data["official_pronouns"] = pronouns
                if sheet.frame == "CONSUME":
                    from girlframe.engine.m3_consume import hunger
                    from girlframe.services.m3_consume_support import appearance

                    data["consume_runtime"] = dict(
                        hunger=hunger(state, prince_sheet_ref(state, sheet.owner))
                        if not sheet.frame_scrapped
                        else "Unavailable (scrapped Frame)",
                        appearance=appearance(state, prince_sheet_ref(state, sheet.owner)),
                    )
            return data

    def helpless_status(self, viewer: GuildViewer) -> bool:
        """Read the current person's condition, including actor-bound NPC opponents."""
        from girlframe.engine.m3_actor_bonds import current_ref, is_helpless

        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) not in state.sheets:
                raise WorkflowError("This Pilot has no activated sheet.")
            return is_helpless(state, current_ref(state, viewer.user_id))

    def activate(
        self, viewer: GuildViewer, key: str, fingerprint: str, public_fields: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        if not set(public_fields) <= PUBLIC_FIELDS or len(set(public_fields)) != len(public_fields):
            raise WorkflowError("Choose supported public fields explicitly.")

        def authorize(c: Connection) -> None:
            self.authorize(c, viewer)
            self.unpaused(c)
            current = CreationReviewService(self.store)._current(c, viewer)
            if (
                current.fingerprint != fingerprint
                or not current.saved_current
                or not current.sheet.ready_for_rules_review
            ):
                raise WorkflowError(
                    "STALE_OR_INCOMPLETE: save a current complete review before activation."
                )

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) in state.sheets:
                raise WorkflowError(
                    "Already activated; activation cannot reset gameplay resources."
                )
            review = CreationReviewService(self.store)._current(c, viewer).sheet
            setup = HandlerService(self.store).current(c)[1]
            from girlframe.engine.m3_careers import binding, profile_character

            current_career = binding(state, viewer.user_id)
            if any(int(x.actor.entity) == viewer.user_id for x in state.career_archives) and (
                current_career is None
                or not current_career.active
                or current_career.status_event is None
            ):
                raise WorkflowError(
                    "The replacement needs its own explicit current-Handler Status assignment."
                )
            absent_careers = {
                int(x.actor.entity)
                for x in state.career_archives
                if int(x.actor.entity) not in state.order
            }
            expected_roster = {x.user_id for x in setup.status_order} - absent_careers
            if not state.order and not state.career_archives:
                state.order = tuple(x.user_id for x in setup.status_order)
                state.handler = setup.handler_id
                state.intense_tag_bonus = self.store.policy.owner_intense_tag_bonus
            elif state.handler != setup.handler_id or set(state.order) != expected_roster:
                raise WorkflowError(
                    "UNSUPPORTED_RULE: canonical roster/Handler changes need explicit migration."
                )
            identities = [
                IdentityState(
                    id="identity:" + str(i),
                    name=name,
                    paired=review.creation.girl_playbook == "BONDED" and name == "Hers",
                    protected=review.creation.girl_playbook == "BONDED" and name == "Hers",
                )
                for i, name in enumerate(review.creation.identities)
            ]
            if review.creation.fanbase:
                identities.extend(
                    IdentityState(id="fan:" + str(i), name=name, protected=True)
                    for i, name in enumerate(review.creation.fanbase.additional_identities)
                )
            assets: list[AssetState] = []
            for family, values in (
                (
                    "girl",
                    review.creation.pair_asset_descriptions
                    if review.creation.girl_playbook == "BONDED"
                    else review.creation.girl_assets,
                ),
                ("frame", review.creation.frame_assets),
            ):
                assets.extend(
                    AssetState(
                        id=family + ":" + str(i),
                        family=cast(Literal["girl", "frame"], family),
                        name=x.name,
                        description=x.description,
                        void=x.name == review.creation.void_asset and family == "girl",
                    )
                    for i, x in enumerate(values)
                )
            assets.extend(
                AssetState(
                    id="frame:intrinsic:" + str(i),
                    family="frame",
                    name=name,
                    intrinsic="wyvern_enormous"
                    if review.creation.frame_playbook == "WYVERN 0.4" and name == "Enormous"
                    else None,
                )
                for i, name in enumerate(review.creation.intrinsic_frame_assets)
            )
            outgoing = next((x for x in review.bonds if x.outgoing), None)
            character_id = c.scalar(
                sa.select(t.characters.c.id).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            )
            if character_id is None:
                raise WorkflowError(
                    "The actual current character profile is required for activation."
                )
            character_id = profile_character(
                state, viewer.user_id, character_id, review.character_revision
            )
            sheet = PilotSheet(
                owner=viewer.user_id,
                character_id=character_id,
                callsign=review.activation_callsign,
                girl=review.creation.girl_playbook,
                frame=review.creation.frame_playbook,
                source_fingerprint=fingerprint,
                source_profile_revision=review.character_revision,
                review=review,
                identities=identities,
                assets=assets,
                heat=review.rulings.starting_heat if review.rulings else 0,
                mentor=outgoing.counterpart
                if outgoing and review.creation.girl_playbook == "NEWGIRL"
                else None,
                pair=outgoing.counterpart
                if outgoing and review.creation.girl_playbook == "BONDED"
                else None,
                public_fields=public_fields,
            )
            state.sheets[str(viewer.user_id)] = sheet
            for bond in review.bonds:
                pair = pair_key(viewer.user_id, bond.counterpart)
                if pair not in state.bonds:
                    state.bonds[pair] = 2 if bond.depth == "Intense" else 1
            from girlframe.engine.m3_actor_bonds import current_ref as activated_actor
            from girlframe.services.m3_vatgrown_death import stage_activation

            activation_event = str(uuid4())
            stage_activation(
                self, c, state, activated_actor(state, viewer.user_id), activation_event
            )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.character_activated",
                state,
                event_id=activation_event,
                owner=viewer.user_id,
            )
            self.store._enqueue_sync(
                c,
                viewer.user_id,
                review.character_revision,
                DraftInput(
                    callsign=sheet.callsign, girl_playbook=sheet.girl, frame_playbook=sheet.frame
                ),
            )
            return {
                "owner": viewer.user_id,
                "revision": sheet.revision,
                "state": "active_m2_subset",
            }

        return self.store._write(
            viewer,
            key,
            "m2.character_activated",
            {"fingerprint": fingerprint, "public_fields": list(public_fields)},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def scene(self, c: Connection, channel: int | str) -> dict[str, Any]:
        table = t.m2["m2_scenes"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                    table.c.open.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Bind an open M2 scene channel first.")
        return dict(row) | {"participants": json.loads(row["participants_json"])}

    def bind_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            self.gate()
            self.store.administrator(viewer)

        def operation(c: Connection) -> dict[str, Any]:
            if type(channel) is not int or not 0 < channel < 2**64:
                raise WorkflowError("Choose an actual server text channel.")
            table = t.m2["m2_scenes"]
            where = sa.and_(
                table.c.campaign_id == self.store.campaign_id, table.c.channel_id == str(channel)
            )
            old = c.execute(sa.select(table).where(where)).mappings().first()
            if old and old["open"]:
                raise WorkflowError("This scene is already open.")
            identity = str(uuid4())
            values = {
                "id": identity,
                "revision": old["revision"] + 1 if old else 1,
                "participants_json": "[]",
                "open": True,
            }
            if old:
                c.execute(table.update().where(where).values(**values))
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            event = self.event(
                c, viewer.user_id, key, "m2.scene_bound", channel=channel, scene_id=identity
            )
            from girlframe.services.m3_work import bind_scene_context

            bind_scene_context(c, self.store, identity, channel, event)
            return {"channel": channel, "scene": identity}

        return self.store._write(
            viewer,
            key,
            "m2.scene_bound",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def join_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) not in state.sheets and viewer.user_id != state.handler:
                raise WorkflowError("Activate a Pilot or use the appointed Handler account.")
            scene = self.scene(c, channel)
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.services.m3_scene_requisitions import guard

            ref = (
                ActorRef(kind="handler", entity=str(viewer.user_id))
                if viewer.user_id == state.handler
                else ActorRef(
                    kind="pilot",
                    entity=str(viewer.user_id),
                    incarnation=self.character_binding(
                        c, state, viewer.user_id, require_current_profile=False
                    ),
                )
            )
            guard(c, self.store, scene["id"], ref)
            if any(x.id == scene["id"] and x.open for x in state.scene_casts):
                raise WorkflowError("Choose your actual role through /mission cast.")
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError(
                    "Wait for this scene's pending Play before changing participants."
                )
            table = t.m2["m2_scenes"]
            if viewer.user_id != state.handler:
                rows = c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id, table.c.open.is_(True)
                    )
                ).mappings()
                if any(
                    x["channel_id"] != str(channel)
                    and viewer.user_id in json.loads(x["participants_json"])
                    for x in rows
                ):
                    raise WorkflowError("A Pilot may join one active M2 scene at a time.")
            people = sorted(set(scene["participants"]) | {viewer.user_id})
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=scene["revision"] + 1)
            )
            self.event(c, viewer.user_id, key, "m2.scene_joined", channel=channel)
            return {"channel": channel, "participants": people}

        return self.store._write(
            viewer,
            key,
            "m2.scene_joined",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def lock(self, c: Connection, channel: int | str) -> dict[str, Any] | None:
        table = t.m2["m2_locks"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def action(self, c: Connection, identity: str) -> dict[str, Any]:
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("Unknown action.") from None
        table = t.m2["m2_actions"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == identity
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Unknown action.")
        return dict(row) | {"data": json.loads(row["body_json"])}

    def save_action(self, c: Connection, action: dict[str, Any], **changes: Any) -> None:
        action.update(changes)
        action["revision"] += 1
        table = t.m2["m2_actions"]
        c.execute(
            table.update()
            .where(table.c.campaign_id == self.store.campaign_id, table.c.id == action["id"])
            .values(
                revision=action["revision"],
                state=action["state"],
                body_json=json.dumps(action["data"], sort_keys=True),
            )
        )

    def request(
        self,
        c: Connection,
        action: dict[str, Any],
        actor: int | None,
        kind: str,
        body: dict[str, Any] | None = None,
    ) -> str:
        if actor is None:
            raise WorkflowError("The required decision owner is unavailable.")
        identity = str(uuid4())
        c.execute(
            t.m2["m2_choices"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=identity,
                action_id=action["id"],
                actor_id=str(actor),
                kind=kind,
                revision=1,
                state="pending",
                body_json=json.dumps(body or {}, sort_keys=True),
            )
        )
        return identity

    def queue(
        self, c: Connection, action: dict[str, Any], kind: str, body: dict[str, Any] | None = None
    ) -> None:
        recipients = action["data"].get("private_audience") or (None,)
        for recipient in recipients:
            identity = str(uuid4())
            payload = {"kind": kind, **(body or {})}
            if recipient is not None:
                payload["private_recipient"] = recipient
            c.execute(
                t.m2["m2_outbox"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    action_id=action["id"],
                    channel_id=action["channel_id"],
                    nonce=str(int(UUID(identity)) % (2**63 - 1)),
                    body_json=json.dumps(payload),
                    state="pending",
                )
            )

    def obligation(
        self,
        state: GameState,
        action: dict[str, Any],
        kind: str,
        owner: int,
        target: int | None = None,
        **details: str,
    ) -> str:
        identity = str(uuid4())
        state.obligations.append(
            Obligation(
                id=identity,
                kind=kind,
                owner=owner,
                target=target,
                action=action["id"],
                details=details,
            )
        )
        return identity

    def pending_actions(self, c: Connection) -> bool:
        from girlframe.services.m3_recovery import pending as pending_recovery

        if pending_recovery(self, c):
            return True
        actions = t.m2["m2_actions"]
        return (
            c.scalar(
                sa.select(actions.c.id)
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.state.not_in(("complete", "aborted")),
                )
                .limit(1)
            )
            is not None
        )

    def director_mode_pending(self, c: Connection, owner: int) -> bool:
        if any(
            x.active and x.handler == owner
            for x in load_state(c, self.store.campaign_id).director_contexts
        ):
            return True
        table = t.m3["m3_required_work"]
        rows = {
            row["id"]: row
            for row in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.subject_id == str(owner),
                    table.c.kind == "director_presence",
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        return any(x["state"] != "resolved" for x in rows.values())

    def character_binding(
        self, c: Connection, state: GameState, owner: int, *, require_current_profile: bool = True
    ) -> str:
        from girlframe.services.m3_incarnations import identity

        return identity(
            c,
            self.store.campaign_id,
            state,
            owner,
            require_current_profile=require_current_profile,
        )

    def action_characters(
        self,
        c: Connection,
        action: dict[str, Any],
        state: GameState,
        *,
        allow_archived: bool = False,
        allowed_archived: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        if action["data"].get("mockingbird", {}).get("play") == "mockingbird_sex":
            from girlframe.services.m3_mockingbird_effects import allowed_archived as sex_archived

            allowed_archived = allowed_archived | sex_archived(self, c, state, action)
        saved = action["data"].get("character_ids")
        if saved is None:
            saved = self.legacy_action_bindings(c, action)
            # Cache only the immutable original bindings already proved below.
            # Read-only callers do not save this local action object.
            action["data"]["character_ids"] = saved
        for owner, original in saved.items():
            if allow_archived or (owner, original) in allowed_archived:
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.engine.m3_careers import archive_for

                if archive_for(state, ActorRef(kind="pilot", entity=owner, incarnation=original)):
                    continue
            if (
                self.character_binding(c, state, int(owner), require_current_profile=False)
                != original
            ):
                raise WorkflowError(
                    "STALE_CHARACTER: this saved decision belongs to an earlier character."
                )

    def pilot_cast(
        self,
        c: Connection,
        state: GameState,
        scene: dict[str, Any],
        *,
        owners: tuple[int, ...] = (),
    ) -> None:
        cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        if cast is None:
            return
        if any(x.actor.kind not in ("pilot", "clone_am") for x in cast.roles):
            raise WorkflowError(
                "UNSUPPORTED_RULE: this mixed-role scene needs its actor-aware Play controls."
            )
        if cast.facilitator != state.handler or set(scene["participants"]) != (
            {x.controller for x in cast.roles} | {cast.facilitator}
        ):
            raise WorkflowError("STALE_CAST: recover the actual scene participation.")
        for owner in owners:
            if owner == state.handler and cast.facilitator == owner:
                continue
            if not any(x.actor.kind == "pilot" and x.controller == owner for x in cast.roles):
                raise WorkflowError(
                    "Join this scene as the actual original Pilot, not only its copy"
                )
        for role in cast.roles:
            if role.actor.kind == "clone_am":
                from girlframe.engine.m3_actors import resolve
                from girlframe.services.m3_actors import profiles
                from girlframe.services.m3_clone_am import prove_copy

                prove_copy(self, c, state, role.actor)
                actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                if actual.controller != role.controller:
                    raise WorkflowError("STALE_CAST: recover the original copy controller")
                continue
            if (
                str(role.controller) != role.actor.entity
                or self.character_binding(c, state, role.controller, require_current_profile=False)
                != role.actor.incarnation
            ):
                raise WorkflowError("STALE_CAST: this role belongs to another character.")

    def legacy_action_bindings(self, c: Connection, action: dict[str, Any]) -> dict[str, str]:
        # Immutable pre-confirmation state and original profile snapshots prove
        # legacy generations, even after a later metadata-only binding/restart.
        confirmed = c.scalar(
            sa.select(t.events.c.seq)
            .where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind.in_(
                    (
                        "m2.play_confirmed",
                        "m3.play_confirmed",
                        "m2.order_issued",
                        "m2.followthrough_confirmed",
                    )
                ),
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
            .order_by(t.events.c.seq)
            .limit(1)
        )
        history = t.m2["m2_state_history"]
        body = (
            c.scalar(
                sa.select(history.c.body_json)
                .select_from(history.join(t.events, history.c.event_id == t.events.c.id))
                .where(history.c.campaign_id == self.store.campaign_id, t.events.c.seq <= confirmed)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if confirmed is not None
            else None
        )
        if body is None:
            raise WorkflowError(
                "LEGACY_ACTION_BINDING: recover the immutable original action state."
            )
        original = GameState.model_validate_json(body)
        result = {}
        for owner in action["data"]["participants"]:
            if owner == action["data"]["handler"]:
                continue
            sheet = original.sheets.get(str(owner))
            if sheet is None:
                raise WorkflowError(
                    "LEGACY_ACTION_BINDING: the original scene character is missing."
                )
            identity = sheet.character_id or c.scalar(
                sa.select(t.snapshots.c.character_id).where(
                    t.snapshots.c.campaign_id == self.store.campaign_id,
                    t.snapshots.c.user_id == str(owner),
                    t.snapshots.c.revision == sheet.source_profile_revision,
                )
            )
            if identity is None:
                raise WorkflowError(
                    "LEGACY_ACTION_BINDING: the original character snapshot is missing."
                )
            result[str(owner)] = identity
        return result

    def immediate_work(
        self,
        c: Connection,
        owner: int,
        *,
        scene_id: str | None = None,
        excluding: frozenset[str] = frozenset(),
    ) -> bool:
        work = t.m3["m3_required_work"]
        latest = {
            row["id"]: row
            for row in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id, work.c.subject_id == str(owner)
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        for row in latest.values():
            if row["id"] in excluding:
                continue
            if row["state"] == "resolved" or not json.loads(row["body_json"]).get("immediate"):
                continue
            if scene_id is not None and row["kind"] == "scene_requisition":
                from girlframe.engine.m3_scene_requisitions import active
                from girlframe.services.m3_scene_requisitions import benefit

                saved = benefit(dict(row))
                if active(saved) and saved.scene is not None and saved.scene.id == scene_id:
                    continue
            return True
        return False

    def begin(
        self, viewer: GuildViewer, key: str, channel: int, sheet_revision: int, prepared: PlayInput
    ) -> dict[str, Any]:
        prepared = PlayInput.model_validate_json(prepared.model_dump_json())
        if prepared.play not in (
            *PLAY_IDS,
            *M3_ROLL_IDS,
            *M3_FIXED_IDS,
            *M3_HEAT_IDS,
            *M3_ASSET_IDS,
            *JANUS_ROLL_IDS,
        ):
            raise WorkflowError("UNSUPPORTED_RULE: this Play is not implemented in M2.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            from girlframe.services.p1_facilitator import require_scene_clear

            if prepared.parent is None:
                require_scene_clear(self, c, channel)
            else:
                require_scene_clear(self, c, channel, self.action(c, prepared.parent))
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_oldgen import require_listened

            require_listened(self, c, state, viewer)
            from girlframe.engine.m3_actor_bonds import current_ref as doll_target_ref
            from girlframe.services.m3_vatgrown import require_attention as require_doll_attention

            doll_target = prepared.target_actor
            if (
                doll_target is None
                and prepared.target is not None
                and str(prepared.target) in state.sheets
            ):
                doll_target = doll_target_ref(state, prepared.target)
            if doll_target is not None:
                require_doll_attention(
                    self, c, state, doll_target, self.scene(c, channel)["id"], "discovery"
                )
            from girlframe.services.m3_princess_sex import child_source

            princess_child = child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_ankou_feedback import prepare_child as prepare_ankou_child

            ankou_child = prepare_ankou_child(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_easy_target import prepare_child as prepare_easy_child

            easy_target_child = prepare_easy_child(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_vatgrown_plays import prepare_investment_performance

            investment_performance = prepare_investment_performance(
                self, c, viewer, state, prepared, channel
            )
            from girlframe.services.m3_prince import (
                flirt_modifier as prince_flirt_modifier,
            )
            from girlframe.services.m3_prince import (
                prepare_demands as prepare_prince_demands,
            )
            from girlframe.services.m3_prince import (
                prepare_exception as prince_exception_source,
            )
            from girlframe.services.m3_prince import (
                prepare_mark as prepare_prince_mark,
            )

            prince_demand_attempt = prince_exception_source(
                self, c, viewer, state, prepared, channel
            )
            prince_mark = prepare_prince_mark(self, c, viewer, state, prepared)
            prince_demands = prepare_prince_demands(self, c, viewer, state, prepared)
            prince_flirt = prince_flirt_modifier(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_consume import prepare_child as consume_child_source

            consume_child = consume_child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_bonded import child_source as bonded_child_source

            bonded_child = bonded_child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_wyvern import prepare_child as wyvern_child_source

            wyvern_child = wyvern_child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_wyvern_combat import (
                prepare_pin_response,
                prepare_replacement,
            )

            wyvern_pin_response = prepare_pin_response(self, c, viewer, state, prepared, channel)
            wyvern_replacement = prepare_replacement(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_red_queen_support import prepare_child as royal_child_source

            red_queen_child = royal_child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_changeling_effects import (
                prepare_child as changeling_child_source,
            )

            changeling_child = changeling_child_source(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_ankou_feedback_sequences import (
                prepare_child as prepare_ankou_effect_child,
            )
            from girlframe.services.m3_required_plays import for_play as required_play_source

            ankou_effect_child = required_play_source(self, c, state, viewer, prepared, channel)
            if ankou_effect_child is None:
                ankou_effect_child = prepare_ankou_effect_child(
                    self, c, viewer, state, prepared, channel
                )
            from girlframe.services.p1_source_pause import require_clear as require_source_clear

            require_source_clear(self, c, channel, prepared=prepared)
            mechanical_owner = (
                int(princess_child["actor_controller"]) if princess_child else viewer.user_id
            )
            if any(x.get("kind") == "fuel_shortage" for x in state.facts):
                from girlframe.engine.m3_actor_bonds import current_ref as fuel_actor
                from girlframe.services.m3_fuel_shortage import require_complete as fuel_complete

                fuel_complete(self, c, state, fuel_actor(state, mechanical_owner))
            from girlframe.engine import m3_void_frame_entry as entry_rules

            void_frame_entry = None
            if entry_rules.records(state, entry_rules.Entry):
                from girlframe.engine.m3_actor_bonds import current_ref as entry_actor
                from girlframe.services.m3_void_frame_entry import (
                    prepare_child as prepare_entry_dive,
                )
                from girlframe.services.m3_void_frame_entry import require_pending

                require_pending(
                    self,
                    c,
                    state,
                    viewer,
                    prepared,
                    actor=entry_actor(state, mechanical_owner),
                )
                void_frame_entry = prepare_entry_dive(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_bonded_rejection import prepare_child as prepare_rejection

            rejection_child = prepare_rejection(self, c, viewer, state, prepared, channel)
            from girlframe.services.m3_npc_flirt import prepare as prepare_npc_flirt

            npc_flirt = (
                prepare_npc_flirt(self, c, viewer, state, prepared, channel)
                if prepared.play == "flirt"
                and prepared.target_actor is not None
                and prepared.target_actor.kind == "npc"
                else None
            )
            prince = None
            consume = None
            bonded = None
            wyvern = None
            red_queen = None
            changeling = None
            ankou = None
            princess_sex = None
            stim_sex = None
            oldgen_sex = None
            casualty_sex = None
            vatgrown_sex = None
            newgirl_sex = None
            easy_target = None
            vatgrown = None
            oldgen = None
            m3 = None
            beneath = None
            defeat = None
            dive = None
            enforcement = None
            battle = None
            engage = None
            mockingbird = None
            snoop = None
            janus = None
            doctor = None
            alpha = None
            alpha_sex = None
            dose_up = None
            am_scrutinized = None
            am_code = None
            alpha_sex_counter_scope = None
            alpha_counter_scope = None
            npc_order_scope = None
            void_keep = None
            dormant_dive_source = None
            from girlframe.services.m3_bomb_collar import (
                prepare_survival as prepare_collar_survival,
            )

            bomb_collar_source = prepare_collar_survival(self, c, state, viewer, prepared, channel)
            from girlframe.services.m3_gorgon_play import (
                prepare_response as prepare_gorgon_response,
            )

            gorgon_response = prepare_gorgon_response(self, c, viewer, prepared, state, channel)
            from girlframe.services.m3_secretary import (
                prepare_response as prepare_secretary_response,
            )

            secretary_scope = prepare_secretary_response(self, c, state, viewer, channel, prepared)
            from girlframe.services.m3_beneath import no_conflict

            no_conflict(self, c, viewer, prepared)
            if prepared.play == "prince_performer":
                from girlframe.services.m3_prince import prepare as prepare_prince

                prince = prepare_prince(self, c, viewer, state, prepared, channel)
            elif prepared.play in (
                "wyvern_explore",
                "wyvern_rouse",
                "wyvern_wraith",
                "wyvern_protector",
            ):
                from girlframe.services.m3_wyvern import prepare as prepare_wyvern

                wyvern = prepare_wyvern(self, c, viewer, state, prepared, channel)
            elif prepared.play == "ankou_processor":
                from girlframe.services.m3_ankou import prepare as prepare_ankou

                ankou = prepare_ankou(self, c, viewer, state, prepared, channel)
            elif prepared.play in ("changeling_blank_slate", "changeling_body_of_clay"):
                from girlframe.services.m3_changeling import prepare as prepare_changeling

                changeling = prepare_changeling(self, c, viewer, state, prepared, channel)
            elif prepared.play in ("red_queen_consult", "red_queen_panopticon", "red_queen_memory"):
                from girlframe.services.m3_red_queen import prepare as prepare_red_queen

                red_queen = prepare_red_queen(self, c, viewer, state, prepared, channel)
            elif prepared.play in ("bonded_side", "bonded_sex"):
                from girlframe.services.m3_bonded import prepare as prepare_bonded

                bonded = prepare_bonded(self, c, viewer, state, prepared, channel)
            elif prepared.play in ("consume_eat", "consume_feral"):
                from girlframe.services.m3_consume import prepare as prepare_consume

                consume = prepare_consume(self, c, viewer, state, prepared, channel)
            if prepared.play in M3_ASSET_IDS:
                from girlframe.services.m3_defeat import prepare as prepare_defeat

                defeat = prepare_defeat(self, c, viewer, prepared, state)
            elif (
                prepared.play == "keep_your_head"
                and prepared.source_work is not None
                and bomb_collar_source is None
                and princess_child is None
                and easy_target_child is None
                and investment_performance is None
                and prince_demand_attempt is None
                and consume_child is None
                and bonded_child is None
                and wyvern_child is None
                and red_queen_child is None
                and rejection_child is None
                and ankou_effect_child is None
                and changeling_child is None
                and wyvern_pin_response is None
                and wyvern_replacement is None
                and bonded is None
                and wyvern is None
                and red_queen is None
                and changeling is None
                and ankou is None
            ):
                from girlframe.services.m3_void_keep import prepare_keep

                void_keep, state = prepare_keep(self, c, viewer, prepared, state, channel)
            elif (
                prepared.play == "dive_deep"
                and prepared.source_work is not None
                and void_frame_entry is None
                and bomb_collar_source is None
                and easy_target_child is None
                and investment_performance is None
                and prince_demand_attempt is None
                and consume_child is None
                and bonded_child is None
                and wyvern_child is None
                and red_queen_child is None
                and rejection_child is None
                and ankou_effect_child is None
                and changeling_child is None
                and wyvern_pin_response is None
                and wyvern_replacement is None
                and bonded is None
                and wyvern is None
                and red_queen is None
                and changeling is None
                and ankou is None
            ):
                from girlframe.services.m3_battle_dormant import prepare_dive_source

                dormant_dive_source = prepare_dive_source(self, c, viewer, prepared, state, channel)
            elif prepared.play in ("mockingbird_person", "mockingbird_sex"):
                from girlframe.services.m3_mockingbird_plays import prepare as prepare_mockingbird

                mockingbird = prepare_mockingbird(self, c, viewer, prepared, state, channel=channel)
            elif (
                prepared.source_work is not None
                and void_frame_entry is None
                and bomb_collar_source is None
                and princess_child is None
                and ankou_child is None
                and easy_target_child is None
                and investment_performance is None
                and prince_demand_attempt is None
                and consume_child is None
                and bonded_child is None
                and wyvern_child is None
                and red_queen_child is None
                and rejection_child is None
                and ankou_effect_child is None
                and changeling_child is None
                and wyvern_pin_response is None
                and wyvern_replacement is None
                and bonded is None
                and wyvern is None
                and red_queen is None
                and changeling is None
                and ankou is None
                and prepared.play
                not in (
                    "prince_performer",
                    "consume_eat",
                    "consume_feral",
                    "alpha_sex",
                    "dose_up",
                    "princess_sex",
                    "stim_sex",
                    "oldgen_sex",
                    "casualty_sex",
                    "vatgrown_sex",
                    "newgirl_sex",
                    "easy_target",
                    "am_scrutinized",
                    "am_just_code",
                )
            ):
                raise WorkflowError("A source work reference belongs to its actual mandatory Play.")
            if prepared.play in ("all_out_assault", "go_for_the_core"):
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.services.m3_battle import prepare as prepare_battle

                battle = prepare_battle(self, c, viewer, state, self.scene(c, channel), prepared)
                actual_battle_actor = ActorRef.model_validate(battle["actor"])
                if (
                    actual_battle_actor.kind != "pilot"
                    or actual_battle_actor.entity != str(mechanical_owner)
                    or actual_battle_actor.incarnation
                    != self.character_binding(
                        c, state, mechanical_owner, require_current_profile=False
                    )
                ):
                    raise WorkflowError(
                        "UNSUPPORTED_BATTLE_ACTOR: use this original role's real resource port; "
                        "a human account's Pilot sheet cannot substitute for it."
                    )
            if (
                prepared.play == "engage"
                and self.store.policy.m3_approval is not None
                and "plays" in self.store.policy.m3_approval.subsystems
            ):
                from girlframe.engine.m3_actor_state import ActorRef as EngageActor
                from girlframe.services.m3_engage import prepare as prepare_engage

                engage = prepare_engage(
                    self,
                    c,
                    viewer,
                    state,
                    self.scene(c, channel),
                    prepared,
                    actor_ref=EngageActor.model_validate(princess_child["actor"])
                    if princess_child
                    else None,
                )
            if prepared.play in JANUS_ROLL_IDS:
                from girlframe.services.m3_janus_play import prepare as prepare_janus

                janus = prepare_janus(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "am_just_code":
                from girlframe.services.m3_am_code import prepare as prepare_am_code

                am_code = prepare_am_code(self, c, viewer, state, prepared, channel)
            if prepared.play == "am_scrutinized":
                from girlframe.services.m3_am_scrutinized import prepare as prepare_am

                am_scrutinized = prepare_am(self, c, viewer, state, prepared, channel)
            if prepared.play == "old_dog_new_pups":
                from girlframe.services.m3_oldgen import prepare as prepare_oldgen

                oldgen = prepare_oldgen(self, c, viewer, state, prepared, channel)
            if prepared.play == "unassuming_doll":
                from girlframe.services.m3_vatgrown import prepare as prepare_doll

                vatgrown = prepare_doll(self, c, viewer, state, prepared, channel)
            if prepared.play == "oldgen_sex":
                from girlframe.services.m3_oldgen_sex import prepare as prepare_oldgen_sex

                oldgen_sex = prepare_oldgen_sex(self, c, viewer, state, prepared, channel)
            if prepared.play == "casualty_sex":
                from girlframe.services.m3_casualty import prepare as prepare_casualty_sex

                casualty_sex = prepare_casualty_sex(self, c, viewer, state, prepared, channel)
            if prepared.play == "vatgrown_sex":
                from girlframe.services.m3_vatgrown_plays import prepare as prepare_vatgrown_sex

                vatgrown_sex = prepare_vatgrown_sex(self, c, viewer, state, prepared, channel)
            if prepared.play == "newgirl_sex":
                from girlframe.services.m3_newgirl_sex import prepare as prepare_newgirl_sex

                newgirl_sex = prepare_newgirl_sex(self, c, viewer, state, prepared, channel)
            if prepared.play == "easy_target":
                from girlframe.services.m3_easy_target import prepare as prepare_easy_target

                easy_target = prepare_easy_target(self, c, viewer, state, prepared, channel)
            if prepared.play == "stim_sex":
                from girlframe.services.m3_stim_sex import prepare as prepare_stim

                stim_sex = prepare_stim(self, c, viewer, state, prepared, channel)
            if prepared.play == "princess_sex":
                from girlframe.services.m3_princess_sex import prepare as prepare_princess

                princess_sex = prepare_princess(self, c, viewer, state, prepared, channel)
            if prepared.play == "dose_up":
                from girlframe.services.m3_dose_up import prepare as prepare_dose

                dose_up = prepare_dose(self, c, viewer, state, prepared, channel)
            if prepared.play == "alpha_sex":
                from girlframe.services.m3_alpha_sex import prepare as prepare_alpha_sex

                alpha_sex = prepare_alpha_sex(self, c, viewer, state, prepared, channel)
            if prepared.play == "brutalize":
                from girlframe.services.m3_alpha import prepare as prepare_alpha

                alpha = prepare_alpha(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "snoop":
                from girlframe.services.m3_enforcer_snoop import prepare as prepare_snoop

                snoop = prepare_snoop(self, c, viewer, prepared, state, channel=channel)
            if prepared.play in ("nanobot_injection", "doctor_support"):
                from girlframe.services.m3_doctor import prepare as prepare_doctor

                doctor = prepare_doctor(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "enforcement_initiative":
                from girlframe.services.m3_enforcement_initiative import (
                    prepare as prepare_enforcement,
                )

                enforcement = prepare_enforcement(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "dive_deep":
                from girlframe.services.m3_dive import prepare as prepare_dive

                dive = prepare_dive(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "put_someone_beneath_you":
                from girlframe.services.m3_beneath import prepare as prepare_beneath

                beneath = prepare_beneath(self, c, viewer, prepared, state)
            if prepared.play in M3_ROLL_IDS:
                from girlframe.services.m3_play_support import prepare

                m3 = prepare(self, c, viewer, prepared)
                from girlframe.services.m3_disposable_psyche import prepare_off_duty

                prepare_off_duty(self, state, mechanical_owner)
            elif prepared.off_duty_id is not None:
                raise WorkflowError("A period reference belongs only to its actual M3 Play.")
            from girlframe.services.m3_adjudication import prepare_required

            adjudication = prepare_required(
                self,
                c,
                viewer,
                prepared,
                state,
                source=defeat or m3 or dormant_dive_source,
                channel=channel,
            )
            if prepared.parent is not None:
                alpha_source = self.action(c, prepared.parent)
                if alpha_source["data"].get("alpha", {}).get("phase") == "counter":
                    from girlframe.engine.m3_actor_bonds import current_ref as alpha_response_ref
                    from girlframe.services.m3_alpha import authorize as authorize_alpha
                    from girlframe.services.m3_alpha import (
                        validate_counter_child as validate_alpha_response,
                    )

                    authorize_alpha(self, c, viewer, alpha_source)
                    validate_alpha_response(
                        self, c, alpha_source, alpha_response_ref(state, mechanical_owner), prepared
                    )
                    alpha_counter_scope = alpha_source["data"]["alpha"]
            if prepared.parent is not None:
                sex_parent = self.action(c, prepared.parent)
                if sex_parent["data"].get("alpha_sex", {}).get("phase") == "counter":
                    from girlframe.engine.m3_actor_bonds import current_ref as sex_response_ref
                    from girlframe.services.m3_alpha_sex import authorize as authorize_sex
                    from girlframe.services.m3_alpha_sex import (
                        validate_counter_child as validate_sex_counter,
                    )

                    authorize_sex(self, c, viewer, sex_parent)
                    validate_sex_counter(
                        self, c, sex_parent, sex_response_ref(state, mechanical_owner), prepared
                    )
                    alpha_sex_counter_scope = sex_parent["data"]["alpha_sex"]
            from girlframe.services.m3_npc_orders import prepare as prepare_npc_order

            npc_order_scope = prepare_npc_order(self, c, state, viewer, channel, prepared)
            sheet = state.sheets.get(str(mechanical_owner))
            if sheet is None or sheet.revision != sheet_revision:
                raise WorkflowError("STALE_SHEET: refresh the Play wizard.")
            if any(x.get("kind") == "a_bomb_drop" for x in state.facts):
                from girlframe.engine.m3_actor_bonds import current_ref as blast_actor
                from girlframe.services.m3_a_bomb import require_damage_cleared

                require_damage_cleared(self, c, state, blast_actor(state, mechanical_owner))
            if any(x.get("kind") == "alpha_sex_session" for x in state.facts):
                from girlframe.engine.m3_actor_bonds import current_ref as sleeping_original
                from girlframe.engine.m3_alpha_sex import require_awake

                require_awake(state, sleeping_original(state, mechanical_owner))
            if sheet.frame_scrapped and prepared.piloting and defeat is None:
                raise WorkflowError(
                    "REQUIRED_FOLLOWUP: replace the scrapped Frame before new Plays."
                )
            from girlframe.services.m3_virus_orders import required_disobey

            virus_order_work = required_disobey(self, c, viewer, state, prepared, channel)
            if (
                self.immediate_work(
                    c,
                    mechanical_owner,
                    scene_id=self.scene(c, channel)["id"],
                    excluding=frozenset(
                        x
                        for x in (
                            virus_order_work,
                            red_queen_child["work"] if red_queen_child else None,
                            bomb_collar_source["work"] if bomb_collar_source else None,
                            void_frame_entry["entry"] if void_frame_entry else None,
                        )
                        if x
                    ),
                )
                and defeat is None
                and void_keep is None
                and dormant_dive_source is None
            ):
                raise WorkflowError(
                    "REQUIRED_FOLLOWUP: replace the scrapped Frame before new Plays."
                    if sheet.frame_scrapped
                    else "REQUIRED_FOLLOWUP: resolve the immediate mechanical follow-up first."
                )
            if sheet.medical_state != "fit" and defeat is None:
                raise WorkflowError("Recover from unconscious injury before a new voluntary Play.")
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.engine.m3_careers import can_pilot

            current_ref = ActorRef(
                kind="pilot",
                entity=str(mechanical_owner),
                incarnation=self.character_binding(
                    c, state, mechanical_owner, require_current_profile=False
                ),
            )
            if (
                not can_pilot(state, current_ref)
                and (
                    prepared.piloting
                    or prepared.play
                    in (
                        "check_sensors",
                        "engage",
                        "dive_deep",
                        "all_out_assault",
                        "go_for_the_core",
                        "enforcement_initiative",
                    )
                )
                and defeat is None
            ):
                raise WorkflowError(
                    "Link Surgery Reversal prevents this original Girl's Frame Plays."
                )
            from girlframe.engine.m3_actor_bonds import is_helpless

            if (
                is_helpless(state, current_ref)
                and defeat is None
                and void_keep is None
                and janus is None
            ):
                raise WorkflowError(
                    "UNSUPPORTED_RULE: recover from Helplessness before a new defensive Play."
                )
            self.character_binding(c, state, mechanical_owner)
            if HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("STALE_HANDLER: canonical Handler replacement needs review.")
            scene = self.scene(c, channel)
            scoped_defeat = False
            if defeat is not None and defeat.get("source_work"):
                from girlframe.services.m3_defeat import work as defeat_work

                source_defeat_work = defeat_work(self, c, defeat["source_work"])
                # prepare_defeat already proves the actual damage fact, original CID and parent.
                scoped_defeat = (
                    isinstance(json.loads(source_defeat_work["body_json"]).get("requirement"), dict)
                    and source_defeat_work["scene_id"] == scene["id"]
                    and prepared.parent is not None
                )
            if (
                all(
                    x is None
                    for x in (
                        dive,
                        void_keep,
                        enforcement,
                        battle,
                        engage,
                        mockingbird,
                        snoop,
                        janus,
                        doctor,
                        alpha,
                        alpha_sex,
                        princess_sex,
                        princess_child,
                        am_scrutinized,
                        am_code,
                        alpha_sex_counter_scope,
                        vatgrown,
                        newgirl_sex,
                        casualty_sex,
                        vatgrown_sex,
                        prince,
                        consume,
                        bonded,
                        wyvern,
                        red_queen,
                        changeling,
                        ankou,
                        bonded_child,
                        wyvern_child,
                        red_queen_child,
                        ankou_effect_child,
                        changeling_child,
                        wyvern_pin_response,
                        wyvern_replacement,
                        easy_target,
                        easy_target_child,
                        alpha_counter_scope,
                        npc_order_scope,
                        gorgon_response,
                        secretary_scope,
                        npc_flirt,
                        rejection_child,
                    )
                )
                and not scoped_defeat
            ):
                self.pilot_cast(
                    c,
                    state,
                    scene,
                    owners=(mechanical_owner,) + ((prepared.target,) if prepared.target else ()),
                )
            else:
                from girlframe.engine.m3_actor_state import SceneCast

                if battle is not None:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    source_cast, _ = CastService(ActorService(MissionService(self.store)))._current(
                        c, state, channel
                    )
                elif rejection_child is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(rejection_child["cast"]))
                elif npc_flirt is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(npc_flirt["cast"]))
                elif princess_sex is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(princess_sex["cast"]))
                elif princess_child is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(princess_child["cast"]))
                elif gorgon_response is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(gorgon_response["cast"]))
                elif secretary_scope is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(secretary_scope["cast"]))
                elif scoped_defeat:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    source_cast, _ = CastService(ActorService(MissionService(self.store)))._current(
                        c, state, channel
                    )
                elif npc_order_scope is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(npc_order_scope["cast"]))
                elif vatgrown is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(vatgrown["cast"]))
                elif newgirl_sex is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(newgirl_sex["cast"]))
                elif casualty_sex is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(casualty_sex["cast"]))
                elif ankou is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(ankou["cast"]))
                elif changeling is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(changeling["cast"]))
                elif changeling_child is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(changeling_child["cast"])
                    )
                elif red_queen is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(red_queen["cast"]))
                elif ankou_effect_child is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(ankou_effect_child["cast"])
                    )
                elif red_queen_child is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(red_queen_child["cast"]))
                elif wyvern is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(wyvern["cast"]))
                elif wyvern_pin_response is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(wyvern_pin_response["cast"])
                    )
                elif wyvern_replacement is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(wyvern_replacement["cast"])
                    )
                elif wyvern_child is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(wyvern_child["cast"]))
                elif bonded is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(bonded["cast"]))
                elif bonded_child is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(bonded_child["cast"]))
                elif prince is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(prince["cast"]))
                elif consume is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(consume["cast"]))
                elif vatgrown_sex is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(vatgrown_sex["cast"]))
                elif easy_target is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(easy_target["cast"]))
                elif easy_target_child is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(easy_target_child["cast"])
                    )
                elif am_code is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(am_code["cast"]))
                elif am_scrutinized is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(am_scrutinized["cast"]))
                elif alpha_sex is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(alpha_sex["cast"]))
                elif alpha_sex_counter_scope is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(alpha_sex_counter_scope["cast"])
                    )
                elif alpha_counter_scope is not None:
                    source_cast = SceneCast.model_validate_json(
                        json.dumps(alpha_counter_scope["cast"])
                    )
                elif alpha is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(alpha["cast"]))
                elif janus is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(janus["cast"]))
                elif doctor is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(doctor["cast"]))
                elif snoop is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(snoop["cast"]))
                elif mockingbird is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(mockingbird["cast"]))
                elif engage is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(engage["cast"]))
                elif enforcement is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(enforcement["cast"]))
                elif dive is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(dive["cast"]))
                else:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    source_cast, _ = CastService(ActorService(MissionService(self.store)))._current(
                        c, state, channel
                    )
                    assert void_keep is not None
                    void_keep["cast"] = source_cast.model_dump(mode="json")
                    void_keep["table"] = sorted(
                        {role.controller for role in source_cast.roles}
                        | ({source_cast.facilitator} if source_cast.facilitator else set())
                    )
                if source_cast.facilitator != state.handler or set(scene["participants"]) != (
                    {
                        role.controller
                        for role in source_cast.roles
                        if role.actor.kind == "pilot" or secretary_scope is not None
                    }
                    | {source_cast.facilitator}
                ):
                    raise WorkflowError(
                        "STALE_CAST: recover the actual Dive participants and facilitator."
                    )
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.services.m3_scene_requisitions import guard as guard_private_scene

            acting_ref = ActorRef(
                kind="pilot",
                entity=str(mechanical_owner),
                incarnation=self.character_binding(
                    c, state, mechanical_owner, require_current_profile=False
                ),
            )
            if defeat is None and void_keep is None:
                from girlframe.services.m3_ankou import require_free as require_ankou_free

                require_ankou_free(
                    self,
                    c,
                    state,
                    acting_ref,
                    ankou_effect_child["id"] if ankou_effect_child else None,
                )
            from girlframe.engine.m3_am import require_freedom, require_harm

            if acting_ref.kind == "pilot" and state.sheets[acting_ref.entity].frame == "CONSUME":
                from girlframe.services.p1_consume_hooks import roll_modifiers as consume_modifiers

                consume_modifiers(self, c, state, acting_ref, prepared)
            from girlframe.services.m3_wyvern_support import wraith_modifiers

            wraith_modifiers(self, c, state, acting_ref, prepared.play)
            if wyvern_pin_response is None:
                from girlframe.services.m3_wyvern_combat import require_free

                require_free(self, c, state, acting_ref)
            from girlframe.services.m3_wyvern_support import require_play_target

            require_play_target(self, c, state, prepared)
            if prepared.play == "disobey_orders":
                require_freedom(state, acting_ref, "refuse")
            if (
                prepared.play in ("brutalize", "alpha_sex", "go_for_the_core")
                and prepared.target_actor is not None
            ):
                require_harm(state, acting_ref, prepared.target_actor)
            if prepared.play == "all_out_assault" and prepared.target_actor is not None:
                from girlframe.engine.m3_am import free as am_free

                if not am_free(state, acting_ref, "harm_humans"):
                    raise WorkflowError(
                        "UNSUPPORTED_AM_HARM_CONTEXT: resolve actual crew "
                        "and human-harm source before Frame combat"
                    )
            guard_private_scene(
                c, self.store, scene["id"], acting_ref, continuation=prepared.parent is not None
            )
            if (
                mechanical_owner not in scene["participants"]
                or state.handler not in scene["participants"]
            ):
                raise WorkflowError("The acting Pilot and Handler must explicitly join this scene.")
            root_lock = self.lock(c, channel)
            parent = None
            counter_source = None
            secretary_response = None
            if prepared.parent:
                parent = self.action(c, prepared.parent)
                if parent["data"].get("gorgon_play"):
                    from girlframe.services.m3_gorgon_play import allowed_archived

                    self.action_characters(
                        c, parent, state, allowed_archived=allowed_archived(self, c, state, parent)
                    )
                else:
                    self.action_characters(c, parent, state)
                from girlframe.services.m3_recovery import authorize as authorize_shared

                authorize_shared(self, c, viewer, parent)
                if (
                    parent["channel_id"] != str(channel)
                    or not root_lock
                    or root_lock["state"] != "held"
                ):
                    raise WorkflowError("An escape Play must use its held parent scene.")
                choices = self.pending(c, parent["id"])
                required = next(
                    (
                        x
                        for x in choices
                        if (
                            x["kind"]
                            in (
                                "escape_play",
                                "secretary_response_play",
                                "order_disobey",
                                "am_prepare",
                                "am_code_prepare",
                                "beneath_response_play",
                                "beneath_defeat",
                                "required_defeat",
                                "defeat_void_threshold",
                                "dive_void_threshold",
                                "enforcer_void_threshold",
                                "battle_item_void_threshold",
                                "battle_defeat",
                                "battle_counter_play",
                                "alpha_counter_play",
                                "alpha_sex_counter_play",
                                "princess_sex_child",
                                "ankou_feedback_child",
                                "consume_child",
                                "wyvern_child",
                                "wyvern_replacement",
                                "changeling_interrupt",
                                "ankou_interrupt_child",
                                "consume_order_child",
                                "easy_target_child",
                                "battle_dormant_dive",
                                "battle_dormant_threshold",
                                "mockingbird_void_threshold",
                                "mockingbird_sex_void_threshold",
                                "janus_void_threshold",
                                "snoop_item_void_threshold",
                                "gorgon_response_play",
                            )
                            or x["kind"].startswith("easy_target_child:")
                        )
                        and x["actor_id"]
                        == str(viewer.user_id if princess_child else mechanical_owner)
                        and (easy_target_child is None or x["id"] == easy_target_child["choice"])
                        and (wyvern_child is None or x["id"] == wyvern_child["choice"])
                        and (
                            ankou_effect_child is None
                            or ankou_effect_child.get("parent") is None
                            or x["id"] == ankou_effect_child["choice"]
                        )
                        and (
                            changeling_child is None
                            or changeling_child["kind"] != "interrupt"
                            or x["id"] == changeling_child["choice"]
                        )
                        and (wyvern_replacement is None or x["id"] == wyvern_replacement["choice"])
                    ),
                    None,
                )
                if required is None:
                    raise WorkflowError("Only the required player can make this response Play.")
                if required["kind"] == "ankou_interrupt_child" and (
                    ankou_effect_child is None
                    or ankou_effect_child.get("parent") != prepared.parent
                ):
                    raise WorkflowError("Use the actual original Relay interrupt source")
                if required["kind"] == "changeling_interrupt" and (
                    changeling_child is None or changeling_child["kind"] != "interrupt"
                ):
                    raise WorkflowError("Use the exact actual original interrupted Play source")
                if required["kind"] == "wyvern_replacement" and wyvern_replacement is None:
                    raise WorkflowError(
                        "Use the genuine incoming Play's original replacement source"
                    )
                if required["kind"] == "wyvern_child" and wyvern_child is None:
                    raise WorkflowError("Use the original Wyvern excursion's actual escape source")
                if required["kind"].startswith("easy_target_child:") and easy_target_child is None:
                    raise WorkflowError("Use the original actual Easy Target reaction performance")
                if (
                    required["kind"] in ("consume_child", "consume_order_child")
                    and consume_child is None
                ):
                    raise WorkflowError(
                        "Use the actual original CONSUME source and required pursuit"
                    )
                if required["kind"] == "ankou_feedback_child" and ankou_child is None:
                    raise WorkflowError("Use the actual Feedback source and its fixed target.")
                if required["kind"] == "princess_sex_child" and princess_child is None:
                    raise WorkflowError("Use this fixed counterpart's actual Princess directive.")
                if required["kind"] == "secretary_response_play":
                    from girlframe.services.m3_secretary import prepare_response as secretary_child

                    secretary_response = secretary_child(self, c, state, viewer, channel, prepared)
                    if secretary_response is None:
                        raise WorkflowError("Use this actual original gunpoint source response")
                if (
                    required["kind"] in ("beneath_defeat", "required_defeat", "battle_defeat")
                    and defeat is None
                ):
                    raise WorkflowError("This actual consequence requires Defeat.")
                if required["kind"] in (
                    "defeat_void_threshold",
                    "dive_void_threshold",
                    "enforcer_void_threshold",
                    "battle_item_void_threshold",
                    "battle_dormant_threshold",
                    "mockingbird_void_threshold",
                    "mockingbird_sex_void_threshold",
                    "janus_void_threshold",
                    "snoop_item_void_threshold",
                ) and (void_keep is None or prepared.play != "keep_your_head"):
                    raise WorkflowError("Use the actual source-owned Void resistance controls.")
                if required["kind"] == "battle_dormant_dive" and dormant_dive_source is None:
                    raise WorkflowError("Use the actual source-owned required Dive controls.")
                if required["kind"] == "alpha_sex_counter_play":
                    from girlframe.services.m3_alpha_sex import (
                        validate_counter_child as validate_sex_child,
                    )

                    sex_counter = validate_sex_child(self, c, parent, acting_ref, prepared)
                if required["kind"] == "alpha_counter_play":
                    from girlframe.services.m3_alpha import (
                        validate_counter_child as validate_alpha_counter,
                    )

                    alpha_counter_actor = ActorRef(
                        kind="pilot",
                        entity=str(mechanical_owner),
                        incarnation=self.character_binding(
                            c, state, mechanical_owner, require_current_profile=False
                        ),
                    )
                    alpha_counter = validate_alpha_counter(
                        self, c, parent, alpha_counter_actor, prepared
                    )
                if required["kind"] == "battle_counter_play":
                    from girlframe.engine.m3_actor_state import ActorRef
                    from girlframe.services.m3_battle import validate_counter_child

                    counter_actor = ActorRef(
                        kind="pilot",
                        entity=str(mechanical_owner),
                        incarnation=self.character_binding(
                            c, state, mechanical_owner, require_current_profile=False
                        ),
                    )
                    actual_counter = validate_counter_child(
                        self, c, parent, counter_actor, prepared
                    )
                    if actual_counter["id"] != required["id"]:
                        raise WorkflowError("Recover the exact actual source counter choice.")
                    counter_body = json.loads(actual_counter["body_json"])
                    counter_source = dict(
                        choice=required["id"],
                        actor=counter_body["actor"],
                        attacker=counter_body["attacker"],
                    )
                if required["kind"] == "gorgon_response_play" and (
                    gorgon_response is None or gorgon_response["choice"] != required["id"]
                ):
                    raise WorkflowError("Use this exact original Gorgon source response")
                if required["kind"] == "am_code_prepare" and (
                    am_code is None
                    or prepared.play != "am_just_code"
                    or parent["data"].get("am_code_source", {}).get("maintenance")
                    != am_code["maintenance"]
                ):
                    raise WorkflowError("Use this actual original circuit-maintenance child")
                if required["kind"] == "am_prepare" and (
                    am_scrutinized is None
                    or prepared.play != "am_scrutinized"
                    or parent["data"].get("am_source", {}).get("discovery")
                    != am_scrutinized["discovery"]
                ):
                    raise WorkflowError("Use this actual original AM's required Scrutinized child")
                if required["kind"] == "order_disobey" and (
                    prepared.play != "disobey_orders"
                    or prepared.order_id != parent["data"]["order_id"]
                ):
                    raise WorkflowError(
                        "Receive Orders requires the actual Disobey Orders response."
                    )
                actions = t.m2["m2_actions"]
                if c.execute(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.parent_id == prepared.parent,
                        actions.c.state.not_in(("complete", "aborted")),
                    )
                ).first():
                    raise WorkflowError(
                        "A response Play already exists; resume it instead of creating another."
                    )
                if parent["data"].get("depth", 0) >= 8:
                    raise WorkflowError(
                        "UNSUPPORTED_RULE: nested response depth requires staff recovery."
                    )
            elif root_lock and root_lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the pending Play first.")
            if prepared.target_actor is not None and all(
                x is None
                for x in (
                    enforcement,
                    battle,
                    engage,
                    mockingbird,
                    snoop,
                    janus,
                    alpha,
                    alpha_sex,
                    dose_up,
                    princess_sex,
                    stim_sex,
                    oldgen_sex,
                    casualty_sex,
                    vatgrown_sex,
                    newgirl_sex,
                    prince,
                    consume,
                    bonded,
                    wyvern,
                    red_queen,
                    changeling,
                    ankou,
                    bonded_child,
                    wyvern_child,
                    red_queen_child,
                    ankou_effect_child,
                    changeling_child,
                    wyvern_pin_response,
                    wyvern_replacement,
                    easy_target,
                    vatgrown,
                    oldgen,
                    am_scrutinized,
                    am_code,
                    doctor,
                    princess_child,
                    npc_flirt,
                    rejection_child,
                )
            ):
                raise WorkflowError("This implemented Play does not take a fictional actor target.")
            if (
                prepared.play
                in (
                    "flirt",
                    "put_someone_beneath_you",
                    "old_dog_new_pups",
                    "unassuming_doll",
                )
                and npc_flirt is None
                and not (vatgrown is not None and prepared.target_actor is not None)
            ):
                if (
                    prepared.target == mechanical_owner
                    or str(prepared.target) not in state.sheets
                    or prepared.target not in scene["participants"]
                ):
                    raise WorkflowError("Choose another active human Pilot in this scene.")
            elif prepared.target is not None:
                raise WorkflowError("This implemented Play does not take a Pilot target.")
            if prepared.play == "engage" and not any(not x.damaged for x in sheet.assets):
                raise WorkflowError("No legal undamaged Asset is available for Engage.")
            if prepared.play == "disobey_orders":
                if prince_demand_attempt is None:
                    self.valid_order(c, state, mechanical_owner, channel, prepared.order_id)
            kicked_puppy = None
            if prepared.play == "flirt" or prepared.kicked_puppy_basis:
                from girlframe.services.m3_kicked_puppy import prepare as prepare_kicked_puppy

                kicked_puppy = prepare_kicked_puppy(self, c, viewer, state, prepared)
            nightmare_core = None
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_nightmare import prepare as prepare_nightmare

                nightmare_core = prepare_nightmare(
                    self, c, viewer, state, prepared, actor=acting_ref
                )
            from girlframe.services.m3_cute_uniforms import prepare_keep as prepare_cute_keep

            cute_uniforms = prepare_cute_keep(self, c, viewer, state, prepared, actor=acting_ref)
            from girlframe.services.m3_disposable_psyche import prepare_disposal

            disposal_permit = prepare_disposal(self, c, state, sheet.owner, prepared)
            if prepared.disposable_heat and (
                (m3 is not None and prepared.play not in ("go_off_duty", "void_observation"))
                or (
                    janus is not None
                    and janus.get("mode") != "pandora"
                    and prepared.play != "living_battery"
                )
            ):
                raise WorkflowError(
                    "UNSUPPORTED_RULE: disposal needs this non-Heat Play's source adapter."
                )
            preview_state = GameState.model_validate_json(state.model_dump_json())
            preview = preview_state.sheets[str(sheet.owner)]
            if prepared.identity:
                from girlframe.engine.m3_clone_am import mark_additional
                from girlframe.services.m3_clone_am import prove_additional

                prove_additional(self, c, state, sheet.owner, prepared.identity)
                share = mark_additional(
                    preview_state, preview, prepared.identity, prepared.gain, prepared.pair_share
                )
                if share is None:
                    share = mark_identity(
                        preview,
                        prepared.identity,
                        prepared.gain,
                        prepared.pair_share,
                        state=preview_state,
                        disposable_heat=prepared.disposable_heat,
                        learned_psyche=disposal_permit,
                    )
                if share and str(sheet.pair) not in state.sheets:
                    raise WorkflowError("The Pair must have an active sheet to receive Heat.")
            elif prepared.gain or prepared.pair_share:
                raise WorkflowError("Heat gain requires an eligible Identity.")
            if (
                m3 is None
                and (janus is None or janus.get("mode") == "pandora")
                and not prepared.kicked_puppy_basis
                and nightmare_core is None
            ):
                spend_heat(preview, prepared.heat)
            dampener = None
            if prepared.dampener_modifier is not None:
                from girlframe.services.m3_dampener import prepare as prepare_dampener

                dampener = prepare_dampener(self, c, viewer, state, prepared)
            identity = str(uuid4())
            data = {
                "prepared": prepared.model_dump(mode="json"),
                "character_ids": {
                    str(uid): self.character_binding(c, state, uid, require_current_profile=False)
                    for uid in scene["participants"]
                    if str(uid) in state.sheets
                },
                "sheet_revision": sheet_revision,
                "play": prepared.play,
                "participants": scene["participants"],
                "depth": parent["data"].get("depth", 0) + 1 if parent else 0,
                "handler": state.handler,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            if prince_demand_attempt is not None:
                data["prince_demand_attempt"] = prince_demand_attempt
            if void_frame_entry is not None:
                data["void_frame_entry"] = void_frame_entry
            if rejection_child is not None:
                from girlframe.engine.m3_handler_consequences import (
                    active_handler as reject_handler,
                )

                actual_handler = reject_handler(state)
                if actual_handler is None:
                    raise WorkflowError("Recover this actual rejection Play's Handler")
                data["bonded_rejection_child"] = rejection_child
                data["participants"] = list(rejection_child["table"])
                data["character_ids"] = {
                    role["actor"]["entity"]: role["actor"]["incarnation"]
                    for role in rejection_child["cast"]["roles"]
                    if role["actor"]["kind"] == "pilot"
                }
                data["tag_context"] = dict(
                    actor=rejection_child["actor"],
                    handler=actual_handler.model_dump(mode="json"),
                    gm_controller=state.handler,
                    table=list(rejection_child["table"]),
                    cast=rejection_child["cast"],
                    cast_sha256=rejection_child["cast_sha256"],
                )
            if npc_flirt is not None:
                from girlframe.engine.m3_handler_consequences import active_handler as flirt_handler

                source_handler = flirt_handler(state)
                if source_handler is None:
                    raise WorkflowError("Recover this Flirt's actual original Handler")
                data["npc_flirt"] = npc_flirt
                data["participants"] = list(npc_flirt["table"])
                data["character_ids"] = {
                    role["actor"]["entity"]: role["actor"]["incarnation"]
                    for role in npc_flirt["cast"]["roles"]
                    if role["actor"]["kind"] == "pilot"
                }
                data["tag_context"] = dict(
                    actor=npc_flirt["actor"],
                    handler=source_handler.model_dump(mode="json"),
                    gm_controller=state.handler,
                    table=list(npc_flirt["table"]),
                    cast=npc_flirt["cast"],
                    cast_sha256=npc_flirt["cast_sha256"],
                )
            if consume_child is not None:
                data["consume_child"] = consume_child
            if bonded_child is not None:
                data["bonded_child"] = bonded_child
            if wyvern_child is not None:
                data["wyvern_child"] = wyvern_child
                data["participants"] = list(wyvern_child["table"])
                data["tag_context"] = dict(
                    actor=wyvern_child["actor"],
                    handler=wyvern_child["handler"],
                    gm_controller=wyvern_child["handler_controller"],
                    table=list(wyvern_child["table"]),
                    cast=wyvern_child["cast"],
                    cast_sha256=wyvern_child["cast_sha256"],
                )
            for counter_name, counter in (
                ("wyvern_pin_response", wyvern_pin_response),
                ("wyvern_replacement", wyvern_replacement),
            ):
                if counter is not None:
                    data[counter_name] = counter
                    data["participants"] = list(counter["table"])
                    data["tag_context"] = dict(
                        actor=counter["actor"],
                        handler=counter["handler"],
                        gm_controller=counter["handler_controller"],
                        table=list(counter["table"]),
                        cast=counter["cast"],
                        cast_sha256=counter["cast_sha256"],
                    )
            if changeling_child is not None:
                from girlframe.engine.m3_handler_consequences import active_handler as child_handler

                actual_handler = child_handler(state)
                if actual_handler is None:
                    raise WorkflowError("Recover the actual source Handler")
                data["changeling_child"] = changeling_child
                data["participants"] = list(changeling_child["table"])
                data["tag_context"] = dict(
                    actor=changeling_child["actor"],
                    handler=actual_handler.model_dump(mode="json"),
                    gm_controller=state.handler,
                    table=list(changeling_child["table"]),
                    cast=changeling_child["cast"],
                    cast_sha256=changeling_child["cast_sha256"],
                )
            if ankou_effect_child is not None:
                from girlframe.engine.m3_handler_consequences import (
                    active_handler as ankou_source_handler,
                )

                source_handler = ankou_source_handler(state)
                if source_handler is None:
                    raise WorkflowError("Recover the actual source Handler")
                data["ankou_effect_child"] = ankou_effect_child
                data["participants"] = sorted(set(ankou_effect_child["table"]) | {state.handler})
                data["tag_context"] = dict(
                    actor=ankou_effect_child["actor"],
                    handler=source_handler.model_dump(mode="json"),
                    gm_controller=state.handler,
                    table=data["participants"],
                    cast=ankou_effect_child["cast"],
                    cast_sha256=ankou_effect_child["cast_sha256"],
                )
            if red_queen_child is not None:
                data["red_queen_child"] = red_queen_child
                data["participants"] = list(red_queen_child["table"])
                data["tag_context"] = dict(
                    actor=red_queen_child["actor"],
                    handler=red_queen_child["handler"],
                    gm_controller=red_queen_child["handler_controller"],
                    table=list(red_queen_child["table"]),
                    cast=red_queen_child["cast"],
                    cast_sha256=red_queen_child["cast_sha256"],
                )
            if prince_mark is not None:
                data["prince_mark"] = prince_mark
            if prince_demands is not None:
                data["prince_demands"] = prince_demands
            if prince_flirt is not None:
                data["prince_flirt"] = prince_flirt
            for book, scope in (
                ("prince", prince),
                ("consume", consume),
                ("bonded", bonded),
                ("wyvern", wyvern),
                ("red_queen", red_queen),
                ("changeling", changeling),
                ("ankou", ankou),
            ):
                if scope is not None:
                    cast = scope["cast"] if book == "prince" else scope["cast"]
                    data[book] = scope
                    data["participants"] = list(scope["table"])
                    data["tag_context"] = dict(
                        actor=scope["actor"],
                        handler=scope["handler"],
                        gm_controller=scope["handler_controller"],
                        table=list(scope["table"]),
                        cast=cast,
                        cast_sha256=scope["cast_sha256"],
                    )
            if ankou_child is not None:
                data["ankou_feedback_child"] = ankou_child
            if investment_performance is not None:
                data["investment_performance"] = investment_performance
            if easy_target_child is not None:
                data["easy_target_child"] = easy_target_child
                from girlframe.engine.m3_actor_state import SceneCast as EasyCast
                from girlframe.engine.m3_actors import fingerprint as easy_fingerprint
                from girlframe.engine.m3_handler_consequences import active_handler as easy_handler

                actual_child_cast = EasyCast.model_validate_json(
                    json.dumps(easy_target_child["cast"])
                )
                original_handler = easy_handler(state)
                data["participants"] = list(easy_target_child["table"])
                data["tag_context"] = dict(
                    actor=easy_target_child["actor"],
                    handler=original_handler.model_dump(mode="json") if original_handler else None,
                    gm_controller=actual_child_cast.facilitator,
                    table=list(easy_target_child["table"]),
                    cast=easy_target_child["cast"],
                    cast_sha256=easy_fingerprint(actual_child_cast),
                )
            if princess_child is not None:
                data["princess_child"] = princess_child
            if oldgen is not None:
                data["oldgen"] = oldgen
                data["participants"] = list(oldgen["table"])
                data["tag_context"] = dict(
                    actor=oldgen["actor"],
                    handler=oldgen["handler"],
                    gm_controller=oldgen["handler_controller"],
                    table=list(oldgen["table"]),
                    cast=oldgen["cast"],
                    cast_sha256=oldgen["cast_sha256"],
                )
            if vatgrown is not None:
                data["vatgrown"] = vatgrown
                data["participants"] = list(vatgrown["table"])
                data["tag_context"] = dict(
                    actor=vatgrown["actor"],
                    handler=vatgrown["handler"],
                    gm_controller=vatgrown["handler_controller"],
                    table=list(vatgrown["table"]),
                    cast=vatgrown["cast"],
                    cast_sha256=vatgrown["cast_sha256"],
                )
            if oldgen_sex is not None:
                data["oldgen_sex"] = oldgen_sex
                data["participants"] = list(oldgen_sex["table"])
                data["tag_context"] = dict(
                    actor=oldgen_sex["actor"],
                    handler=oldgen_sex["handler"],
                    gm_controller=oldgen_sex["handler_controller"],
                    table=list(oldgen_sex["table"]),
                    cast=oldgen_sex["cast"],
                    cast_sha256=oldgen_sex["cast_sha256"],
                )
            if casualty_sex is not None:
                data["casualty_sex"] = casualty_sex
                data["participants"] = list(casualty_sex["table"])
                data["tag_context"] = dict(
                    actor=casualty_sex["actor"],
                    handler=casualty_sex["handler"],
                    gm_controller=casualty_sex["handler_controller"],
                    table=list(casualty_sex["table"]),
                    cast=casualty_sex["cast"],
                    cast_sha256=casualty_sex["cast_sha256"],
                )
            if vatgrown_sex is not None:
                data["vatgrown_sex"] = vatgrown_sex
                data["participants"] = list(vatgrown_sex["table"])
                data["tag_context"] = dict(
                    actor=vatgrown_sex["actor"],
                    handler=vatgrown_sex["handler"],
                    gm_controller=vatgrown_sex["handler_controller"],
                    table=list(vatgrown_sex["table"]),
                    cast=vatgrown_sex["cast"],
                    cast_sha256=vatgrown_sex["cast_sha256"],
                )
            if newgirl_sex is not None:
                data["newgirl_sex"] = newgirl_sex
                data["participants"] = list(newgirl_sex["table"])
                data["tag_context"] = dict(
                    actor=newgirl_sex["actor"],
                    handler=newgirl_sex["handler"],
                    gm_controller=newgirl_sex["handler_controller"],
                    table=list(newgirl_sex["table"]),
                    cast=newgirl_sex["cast"],
                    cast_sha256=newgirl_sex["cast_sha256"],
                )
            if easy_target is not None:
                data["easy_target"] = easy_target
                data["participants"] = list(easy_target["table"])
                data["tag_context"] = dict(
                    actor=easy_target["actor"],
                    handler=easy_target["handler"],
                    gm_controller=easy_target["handler_controller"],
                    table=list(easy_target["table"]),
                    cast=easy_target["cast"],
                    cast_sha256=easy_target["cast_sha256"],
                )
            if stim_sex is not None:
                data["stim_sex"] = stim_sex
                data["participants"] = list(stim_sex["table"])
                data["tag_context"] = dict(
                    actor=stim_sex["actor"],
                    handler=stim_sex["handler"],
                    gm_controller=stim_sex["handler_controller"],
                    table=list(stim_sex["table"]),
                    cast=stim_sex["cast"],
                    cast_sha256=stim_sex["cast_sha256"],
                )
            if princess_sex is not None:
                from girlframe.engine.m3_actor_state import SceneCast as PrincessCast
                from girlframe.engine.m3_actors import fingerprint as princess_fingerprint
                from girlframe.engine.m3_handler_consequences import active_handler

                princess_handler = active_handler(state)
                data["princess_sex"] = princess_sex
                data["participants"] = list(princess_sex["table"])
                data["tag_context"] = dict(
                    actor=princess_sex["actor"],
                    handler=(
                        princess_handler.model_dump(mode="json") if princess_handler else None
                    ),
                    gm_controller=state.handler,
                    table=list(princess_sex["table"]),
                    cast=princess_sex["cast"],
                    cast_sha256=princess_fingerprint(
                        PrincessCast.model_validate_json(json.dumps(princess_sex["cast"]))
                    ),
                )
            if dampener is not None:
                data["dampener"] = dampener
            if kicked_puppy is not None:
                data["kicked_puppy"] = kicked_puppy
            if nightmare_core is not None:
                data["nightmare_core"] = nightmare_core
            if cute_uniforms is not None:
                data["cute_uniforms"] = cute_uniforms
            from girlframe.services.m3_scene_requisitions import audience as private_scene_audience

            private_audience = private_scene_audience(c, self.store, scene["id"])
            if private_audience is not None:
                data["private_audience"] = list(private_audience)
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_enforcer_requisitions import (
                    prepare_keep as prepare_pavlov,
                )

                data["enforcer_keep"] = prepare_pavlov(self, c, state, acting_ref, prepared)
            if bomb_collar_source is not None:
                data["bomb_collar_source"] = bomb_collar_source
            if dormant_dive_source is not None:
                data["dormant_dive_source"] = dormant_dive_source
            if m3 is not None:
                data["m3"] = m3
            if beneath is not None:
                data["beneath"] = beneath
            if defeat is not None:
                data["defeat"] = defeat
            if scoped_defeat:
                from girlframe.engine.m3_actors import fingerprint
                from girlframe.engine.m3_handler_consequences import active_handler

                assert defeat is not None
                handler_body = active_handler(state)
                table_humans = sorted(
                    {x.controller for x in source_cast.roles}
                    | ({source_cast.facilitator} if source_cast.facilitator else set())
                )
                data["participants"] = table_humans
                data["tag_context"] = dict(
                    actor=defeat["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=state.handler,
                    table=table_humans,
                    cast=source_cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(source_cast),
                )
            if gorgon_response is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["gorgon_counter_source"] = {
                    k: gorgon_response[k] for k in ("choice", "actor", "attacker")
                }
                data["participants"] = list(gorgon_response["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=gorgon_response["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=state.handler,
                    table=list(gorgon_response["table"]),
                    cast=gorgon_response["cast"],
                    cast_sha256=gorgon_response["cast_sha256"],
                )
            if (
                parent is not None
                and parent["data"].get("alpha")
                and required is not None
                and required["kind"] == "alpha_counter_play"
            ):
                data["alpha_counter_source"] = alpha_counter
            if counter_source is not None:
                data["battle_counter_source"] = counter_source
            if battle is not None:
                from girlframe.engine.m3_actors import fingerprint
                from girlframe.engine.m3_handler_consequences import active_handler

                data["battle"] = battle
                data["handler"] = battle["handler"]
                data["participants"] = list(battle["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=battle["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=battle["procedural_gm"],
                    table=list(battle["table"]),
                    cast=source_cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(source_cast),
                )
            if engage is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["engage"] = engage
                data["participants"] = list(engage["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=engage["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=state.handler,
                    table=list(engage["table"]),
                    cast=engage["cast"],
                    cast_sha256=engage["cast_sha256"],
                )
            if npc_order_scope is not None:
                from girlframe.engine.m3_actors import fingerprint
                from girlframe.engine.m3_handler_consequences import active_handler

                data["npc_order"] = npc_order_scope
                data["character_ids"] = {
                    str(x.controller): x.actor.incarnation
                    for x in source_cast.roles
                    if x.actor.kind == "pilot"
                }
                npc_source_table = sorted(
                    {x.controller for x in source_cast.roles}
                    | ({source_cast.facilitator} if source_cast.facilitator is not None else set())
                )
                data["participants"] = npc_source_table
                body = active_handler(state)
                data["tag_context"] = dict(
                    actor=acting_ref.model_dump(mode="json"),
                    handler=body.model_dump(mode="json") if body else None,
                    gm_controller=state.handler,
                    table=npc_source_table,
                    cast=source_cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(source_cast),
                )
            if am_code is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["am_code"] = am_code
                data["participants"] = list(am_code["table"])
                code_handler = active_handler(state)
                data["tag_context"] = dict(
                    actor=am_code["actor"],
                    handler=code_handler.model_dump(mode="json") if code_handler else None,
                    gm_controller=state.handler,
                    table=list(am_code["table"]),
                    cast=am_code["cast"],
                    cast_sha256=am_code["cast_sha256"],
                )
            if am_scrutinized is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["am_scrutinized"] = am_scrutinized
                data["participants"] = list(am_scrutinized["table"])
                am_handler = active_handler(state)
                data["tag_context"] = dict(
                    actor=am_scrutinized["actor"],
                    handler=am_handler.model_dump(mode="json") if am_handler else None,
                    gm_controller=state.handler,
                    table=list(am_scrutinized["table"]),
                    cast=am_scrutinized["cast"],
                    cast_sha256=am_scrutinized["cast_sha256"],
                )
            if alpha_sex is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["alpha_sex"] = alpha_sex
                data["participants"] = list(alpha_sex["table"])
                sex_handler = active_handler(state)
                data["tag_context"] = dict(
                    actor=alpha_sex["actor"],
                    handler=sex_handler.model_dump(mode="json") if sex_handler else None,
                    gm_controller=state.handler,
                    table=list(alpha_sex["table"]),
                    cast=alpha_sex["cast"],
                    cast_sha256=alpha_sex["cast_sha256"],
                )
            if dose_up is not None:
                from girlframe.engine.m3_actor_state import SceneCast as DoseCast
                from girlframe.engine.m3_actors import fingerprint as dose_fingerprint

                data["dose_up"] = dose_up
                data["participants"] = list(dose_up["table"])
                data["tag_context"] = dict(
                    actor=dose_up["actor"],
                    handler=dose_up["handler"],
                    gm_controller=dose_up["handler_controller"],
                    table=list(dose_up["table"]),
                    cast=dose_up["cast"],
                    cast_sha256=dose_fingerprint(
                        DoseCast.model_validate_json(json.dumps(dose_up["cast"]))
                    ),
                )
            if alpha_sex_counter_scope is not None:
                data["alpha_sex_counter_source"] = sex_counter
                data["participants"] = list(alpha_sex_counter_scope["table"])
                from girlframe.engine.m3_handler_consequences import active_handler

                sex_handler = active_handler(state)
                data["tag_context"] = dict(
                    actor=acting_ref.model_dump(mode="json"),
                    handler=sex_handler.model_dump(mode="json") if sex_handler else None,
                    gm_controller=state.handler,
                    table=list(alpha_sex_counter_scope["table"]),
                    cast=alpha_sex_counter_scope["cast"],
                    cast_sha256=alpha_sex_counter_scope["cast_sha256"],
                )
            if alpha is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["alpha"] = alpha
                data["participants"] = list(alpha["table"])
                body = active_handler(state)
                data["tag_context"] = dict(
                    actor=alpha["actor"],
                    handler=body.model_dump(mode="json") if body else None,
                    gm_controller=state.handler,
                    table=list(alpha["table"]),
                    cast=alpha["cast"],
                    cast_sha256=alpha["cast_sha256"],
                )
            if janus is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["janus"] = janus
                data["participants"] = list(janus["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=janus["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=state.handler,
                    table=list(janus["table"]),
                    cast=janus["cast"],
                    cast_sha256=janus["cast_sha256"],
                )
            if doctor is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["doctor"] = doctor
                data["participants"] = list(doctor["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=doctor["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=doctor["procedural_gm"],
                    table=list(doctor["table"]),
                    cast=doctor["cast"],
                    cast_sha256=doctor["cast_sha256"],
                )
            if snoop is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["snoop"] = snoop
                data["participants"] = list(snoop["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=snoop["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=snoop["procedural_gm"],
                    table=list(snoop["table"]),
                    cast=snoop["cast"],
                    cast_sha256=snoop["cast_sha256"],
                )
            if mockingbird is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                data["mockingbird"] = mockingbird
                data["participants"] = list(mockingbird["table"])
                handler_body = active_handler(state)
                data["tag_context"] = dict(
                    actor=mockingbird["actor"],
                    handler=handler_body.model_dump(mode="json") if handler_body else None,
                    gm_controller=state.handler,
                    table=list(mockingbird["table"]),
                    cast=mockingbird["cast"],
                    cast_sha256=mockingbird["cast_sha256"],
                )
            if enforcement is not None:
                data["enforcement"] = enforcement
                data["participants"] = list(enforcement["table"])
            if dive is not None:
                data["dive"] = dive
                data["participants"] = list(dive["table"])
            if adjudication is not None:
                data["adjudication"] = adjudication
            if void_keep is not None:
                data["void_keep"] = void_keep
                data["participants"] = list(void_keep["table"])
            if secretary_response is not None:
                data["secretary_response"] = secretary_response
            from girlframe.services.m3_recovery import enable as enable_recovery

            enable_recovery(self, c, viewer, data)
            if prepared.play == "disobey_orders":
                actual_order = (
                    self.valid_order(c, state, mechanical_owner, channel, prepared.order_id)
                    if prince_demand_attempt is None
                    else {"body_json": "{}"}
                )
                source_departure = json.loads(actual_order["body_json"]).get("vatgrown_leaving")
                if source_departure is not None:
                    data["vatgrown_leaving"] = source_departure
                from girlframe.services.m3_refusal import prepare as prepare_refusal

                data["m3_refusal"] = prepare_refusal(self, c, viewer, state)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(mechanical_owner),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=prepared.parent,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            action = self.action(c, identity)
            if parent:
                self.save_action(c, action, state="ready_to_roll")
            else:
                table = t.m2["m2_locks"]
                values = {
                    "action_id": identity,
                    "state": "acquiring",
                    "body_json": "{}",
                    "lease_until": 0,
                    "claim_token": None,
                }
                if root_lock:
                    c.execute(
                        table.update()
                        .where(
                            table.c.campaign_id == self.store.campaign_id,
                            table.c.channel_id == str(channel),
                        )
                        .values(**values)
                    )
                else:
                    c.execute(
                        table.insert().values(
                            campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                        )
                    )
            if am_code is not None:
                from girlframe.services.m3_am_code import bind as bind_am_code

                bind_am_code(state, self.action(c, identity))
            if am_scrutinized is not None:
                from girlframe.services.m3_am_scrutinized import bind as bind_am

                bind_am(state, self.action(c, identity))
            if alpha_sex is not None:
                from girlframe.services.m3_alpha_sex import bind as bind_alpha_sex

                bind_alpha_sex(state, self.action(c, identity))
            if (mockingbird or {}).get("learned_sex_source"):
                from girlframe.services.m3_mockingbird_plays import bind as bind_mockingbird_sex

                bind_mockingbird_sex(state, self.action(c, identity))
            appearance_reset = False
            if m3 is not None and prepared.play in ("go_off_duty", "void_observation"):
                from girlframe.engine.m3_appearance_matrix import reset_at_start

                appearance_reset = reset_at_start(state, acting_ref, m3["period_id"], identity)
            marriage_cast_saved = False
            if prepared.play == "flirt" and data.get("actor_basic") is None:
                from girlframe.engine.m3_intracadre_marriage import marriage_for
                from girlframe.services.m3_intracadre_marriage import prove as prove_marriage

                marriage = marriage_for(state, acting_ref)
                if marriage is not None:
                    prove_marriage(self, c, state, marriage.id)
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    source_cast, legacy_cast = CastService(
                        ActorService(MissionService(self.store))
                    )._current(c, state, channel)
                    if legacy_cast:
                        state.scene_casts.append(source_cast)
                        marriage_cast_saved = True
            from girlframe.services.m3_changeling_sex import for_play as remote_sex_source

            remote_sex_link = remote_sex_source(self, c, state, action)
            begin_source_event = (
                str(uuid4())
                if remote_sex_link is not None
                or secretary_response is not None
                or princess_child
                or princess_sex
                or stim_sex
                or oldgen_sex
                or casualty_sex
                or vatgrown_sex
                or npc_flirt
                or rejection_child
                or void_frame_entry
                or prince
                or consume
                or prince_demand_attempt
                or consume_child
                or bonded
                or wyvern
                or red_queen
                or changeling
                or ankou
                or bonded_child
                or wyvern_child
                or red_queen_child
                or ankou_effect_child
                or changeling_child
                or wyvern_pin_response
                or wyvern_replacement
                or newgirl_sex
                or easy_target
                or easy_target_child
                or ankou_child
                or investment_performance
                else None
            )
            from girlframe.engine.m3_ankou import Task as AnkouTask
            from girlframe.engine.m3_ankou import records as ankou_tasks
            from girlframe.services.m3_ankou import on_play as stage_ankou_play

            ankou_begin_event = begin_source_event or str(uuid4())
            stage_ankou_play(self, c, state, action, ankou_begin_event)
            if any(x.event == ankou_begin_event for x in ankou_tasks(state, AnkouTask)):
                begin_source_event = ankou_begin_event
                action["data"]["ankou_source_tasks"] = ankou_begin_event
                self.save_action(c, action)
            from girlframe.services.m3_learned_plays import claim as claim_learned_play

            claimed_learned = claim_learned_play(
                self, c, state, action, begin_source_event or str(uuid4())
            )
            if claimed_learned:
                begin_source_event = action["data"]["learned_play"]["event"]
                action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                self.save_action(c, action)
            from girlframe.services.m3_learned_plays import reserve_triggered

            triggered_learning = reserve_triggered(
                self, c, state, action, begin_source_event or str(uuid4())
            )
            if triggered_learning:
                begin_source_event = action["data"]["learned_no_one_better"]["event"]
                action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                self.save_action(c, action)
                claimed_learned = True
            if prepared.learned_keep_rider is not None:
                from girlframe.services.m3_learned_plays import reserve_keep_rider

                if reserve_keep_rider(self, c, state, action, begin_source_event or str(uuid4())):
                    begin_source_event = action["data"]["learned_keep_rider"]["event"]
                    action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                    self.save_action(c, action)
                    claimed_learned = True
            if prepared.learned_call is not None:
                from girlframe.services.m3_learned_plays import reserve_call_lesson

                if reserve_call_lesson(self, c, state, action, begin_source_event or str(uuid4())):
                    begin_source_event = action["data"]["learned_call"]["event"]
                    action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                    self.save_action(c, action)
                    claimed_learned = True
            if prepared.learned_show_dog is not None or prepared.learned_psyche is not None:
                from girlframe.services.m3_learned_plays import reserve_daily_lessons

                if reserve_daily_lessons(
                    self, c, state, action, begin_source_event or str(uuid4())
                ):
                    daily_source = (
                        action["data"].get("learned_show_dog") or action["data"]["learned_psyche"]
                    )
                    begin_source_event = daily_source["event"]
                    action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                    self.save_action(c, action)
                    claimed_learned = True
            if prince_demand_attempt is not None:
                from girlframe.services.m3_prince import bind_exception

                assert begin_source_event is not None
                bind_exception(state, action, begin_source_event)
            if prince is not None:
                from girlframe.services.m3_prince import bind as bind_prince

                assert begin_source_event is not None
                bind_prince(state, action, begin_source_event)
            if consume is not None:
                from girlframe.services.m3_consume import bind as bind_consume

                assert begin_source_event is not None
                bind_consume(state, action, begin_source_event)
            if remote_sex_link is not None:
                from girlframe.services.m3_changeling_sex import bind_action as bind_remote_source

                assert begin_source_event is not None
                bind_remote_source(self, c, state, action, begin_source_event)
                self.save_action(c, action)
            from girlframe.services.m3_changeling import reserve_flirt

            flirt_begin = begin_source_event or str(uuid4())
            reserve_flirt(self, c, state, action, flirt_begin)
            if action["data"].get("changeling_flirt"):
                begin_source_event = flirt_begin
                self.save_action(c, action)
            if ankou is not None:
                from girlframe.services.m3_ankou import bind as bind_ankou

                assert begin_source_event is not None
                bind_ankou(state, action, begin_source_event)
            if changeling is not None:
                from girlframe.services.m3_changeling import bind as bind_changeling

                assert begin_source_event is not None
                bind_changeling(state, action, begin_source_event)
            if changeling_child is not None:
                from girlframe.services.m3_changeling_effects import (
                    bind_child as bind_changeling_child,
                )

                assert begin_source_event is not None
                bind_changeling_child(self, c, state, action, begin_source_event)
            if red_queen is not None:
                from girlframe.services.m3_red_queen import bind as bind_red_queen

                assert begin_source_event is not None
                bind_red_queen(state, action, begin_source_event)
            if ankou_effect_child is not None:
                from girlframe.services.m3_ankou_feedback_sequences import (
                    bind_child as bind_ankou_effect_child,
                )

                assert begin_source_event is not None
                bind_ankou_effect_child(self, c, state, action, begin_source_event)
            if rejection_child is not None:
                from girlframe.services.m3_bonded_rejection import bind_child as bind_rejection

                assert begin_source_event is not None
                bind_rejection(self, c, state, action, begin_source_event)
                self.save_action(c, action)
            if npc_flirt is not None:
                from girlframe.services.m3_npc_flirt import bind as bind_npc_flirt

                assert begin_source_event is not None
                bind_npc_flirt(self, c, state, action, begin_source_event)
                self.save_action(c, action)
            if begin_source_event is not None:
                from girlframe.services.m3_required_plays import bind_action as bind_required_play

                bind_required_play(self, c, state, action, begin_source_event)
            if void_frame_entry is not None:
                from girlframe.services.m3_void_frame_entry import bind_child as bind_entry_dive

                assert begin_source_event is not None
                bind_entry_dive(self, c, state, action, begin_source_event)
                self.save_action(c, action)
            if red_queen_child is not None:
                from girlframe.services.m3_red_queen_support import bind_child as bind_royal_child

                assert begin_source_event is not None
                bind_royal_child(self, c, state, action, begin_source_event)
            if wyvern is not None:
                from girlframe.services.m3_wyvern import bind as bind_wyvern

                assert begin_source_event is not None
                bind_wyvern(state, action, begin_source_event)
            if wyvern_pin_response is not None:
                from girlframe.services.m3_wyvern_combat import bind_pin_response

                assert begin_source_event is not None
                bind_pin_response(self, c, state, action, begin_source_event)
            if wyvern_replacement is not None:
                from girlframe.services.m3_wyvern_combat import bind_replacement

                assert begin_source_event is not None
                bind_replacement(self, c, state, action, begin_source_event)
            if wyvern_child is not None:
                from girlframe.services.m3_wyvern import bind_child as bind_wyvern_child

                assert begin_source_event is not None
                bind_wyvern_child(self, c, state, action, begin_source_event)
            if bonded is not None:
                from girlframe.services.m3_bonded import bind as bind_bonded

                assert begin_source_event is not None
                bind_bonded(state, action, begin_source_event)
            if bonded_child is not None:
                from girlframe.services.m3_bonded import bind_child as bind_bonded_child

                assert begin_source_event is not None
                bind_bonded_child(self, c, state, action, begin_source_event)
            if consume_child is not None:
                from girlframe.services.m3_consume import bind_child as bind_consume_child

                assert begin_source_event is not None
                bind_consume_child(self, c, state, action, begin_source_event)
            if investment_performance is not None:
                from girlframe.services.m3_vatgrown_plays import bind_investment_performance

                assert begin_source_event is not None
                bind_investment_performance(self, c, state, action, begin_source_event)
            if easy_target_child is not None:
                from girlframe.services.m3_easy_target import bind_child as bind_easy_child

                assert begin_source_event is not None
                bind_easy_child(self, c, state, action, begin_source_event)
            if ankou_child is not None:
                from girlframe.services.m3_ankou_feedback import bind_child as bind_ankou_child

                assert begin_source_event is not None
                bind_ankou_child(self, c, state, action, begin_source_event)
            if princess_child is not None:
                from girlframe.services.m3_princess_sex import bind_child

                assert begin_source_event is not None
                bind_child(self, c, state, action, begin_source_event)
            if oldgen_sex is not None:
                from girlframe.services.m3_oldgen_sex import bind as bind_oldgen_sex

                bind_oldgen_sex(state, action, begin_source_event)
            if casualty_sex is not None:
                from girlframe.services.m3_casualty import bind as bind_casualty_sex

                bind_casualty_sex(state, action, begin_source_event)
            if vatgrown_sex is not None:
                from girlframe.services.m3_vatgrown_plays import bind as bind_vatgrown_sex

                bind_vatgrown_sex(state, action, begin_source_event)
            if newgirl_sex is not None:
                from girlframe.services.m3_newgirl_sex import bind as bind_newgirl_sex

                bind_newgirl_sex(state, action, begin_source_event)
            if stim_sex is not None:
                from girlframe.services.m3_stim_sex import bind as bind_stim

                bind_stim(state, action, begin_source_event)
            if princess_sex is not None:
                from girlframe.services.m3_princess_sex import bind as bind_princess

                bind_princess(state, action, begin_source_event)
            from girlframe.services.m3_learned_sex import bind_action as bind_learned_sex
            from girlframe.services.m3_learned_sex import source_id as learned_sex_id

            if learned_sex_id(action) is not None:
                begin_source_event = begin_source_event or str(uuid4())
                if bind_learned_sex(self, c, state, action, begin_source_event):
                    action["data"]["sheet_revision"] = state.sheets[str(mechanical_owner)].revision
                    self.save_action(c, action)
                    claimed_learned = True
            if secretary_response is not None:
                from girlframe.services.m3_secretary import link_response

                assert begin_source_event is not None
                link_response(state, secretary_response["gunpoint"], identity, begin_source_event)
            event = self.event(
                c,
                viewer.user_id,
                key,
                "m3.play_confirmed"
                if m3 is not None
                or beneath is not None
                or defeat is not None
                or dive is not None
                or enforcement is not None
                or battle is not None
                or mockingbird is not None
                or snoop is not None
                or janus is not None
                or doctor is not None
                or alpha is not None
                or alpha_sex is not None
                or dose_up is not None
                or princess_sex is not None
                or stim_sex is not None
                or oldgen_sex is not None
                or casualty_sex is not None
                or vatgrown_sex is not None
                or npc_flirt is not None
                or rejection_child is not None
                or prince is not None
                or consume is not None
                or prince_demand_attempt is not None
                or consume_child is not None
                or bonded is not None
                or wyvern is not None
                or red_queen is not None
                or action["data"].get("ankou_pulse")
                or action["data"].get("ankou_roll_modifiers")
                or action["data"].get("ankou_source_tasks")
                or action["data"].get("changeling_remote")
                or action["data"].get("changeling_flirt")
                or changeling is not None
                or ankou is not None
                or bonded_child is not None
                or wyvern_child is not None
                or red_queen_child is not None
                or ankou_effect_child is not None
                or changeling_child is not None
                or wyvern_pin_response is not None
                or wyvern_replacement is not None
                or newgirl_sex is not None
                or easy_target is not None
                or easy_target_child is not None
                or vatgrown is not None
                or oldgen is not None
                or princess_child is not None
                or ankou_child is not None
                or prepared.disposable_heat
                or am_scrutinized is not None
                or am_code is not None
                or npc_order_scope is not None
                or engage is not None
                or void_keep is not None
                or dampener is not None
                or kicked_puppy is not None
                or nightmare_core is not None
                or cute_uniforms is not None
                else "m2.play_confirmed",
                state
                if (
                    void_frame_entry is not None
                    or void_keep is not None
                    or alpha_sex is not None
                    or dose_up is not None
                    or princess_sex is not None
                    or stim_sex is not None
                    or oldgen_sex is not None
                    or casualty_sex is not None
                    or vatgrown_sex is not None
                    or npc_flirt is not None
                    or rejection_child is not None
                    or prince is not None
                    or consume is not None
                    or prince_demand_attempt is not None
                    or consume_child is not None
                    or bonded is not None
                    or wyvern is not None
                    or red_queen is not None
                    or action["data"].get("ankou_pulse")
                    or action["data"].get("ankou_roll_modifiers")
                    or action["data"].get("ankou_source_tasks")
                    or action["data"].get("changeling_remote")
                    or action["data"].get("changeling_flirt")
                    or changeling is not None
                    or ankou is not None
                    or bonded_child is not None
                    or wyvern_child is not None
                    or red_queen_child is not None
                    or ankou_effect_child is not None
                    or changeling_child is not None
                    or wyvern_pin_response is not None
                    or wyvern_replacement is not None
                    or newgirl_sex is not None
                    or easy_target is not None
                    or easy_target_child is not None
                    or vatgrown is not None
                    or oldgen is not None
                    or princess_child is not None
                    or ankou_child is not None
                    or am_scrutinized is not None
                    or am_code is not None
                    or appearance_reset
                    or marriage_cast_saved
                    or secretary_response is not None
                    or claimed_learned
                    or npc_flirt is not None
                    or rejection_child is not None
                    or prince is not None
                    or consume is not None
                    or prince_demand_attempt is not None
                    or consume_child is not None
                    or bonded is not None
                    or wyvern is not None
                    or red_queen is not None
                    or action["data"].get("ankou_pulse")
                    or action["data"].get("ankou_roll_modifiers")
                    or action["data"].get("ankou_source_tasks")
                    or action["data"].get("changeling_remote")
                    or action["data"].get("changeling_flirt")
                    or changeling is not None
                    or ankou is not None
                    or bonded_child is not None
                    or wyvern_child is not None
                    or red_queen_child is not None
                    or ankou_effect_child is not None
                    or changeling_child is not None
                    or wyvern_pin_response is not None
                    or wyvern_replacement is not None
                    or investment_performance is not None
                )
                else None,
                event_id=begin_source_event,
                action_id=identity,
                play=prepared.play,
            )
            if m3 is not None:
                from girlframe.services.m3_play_support import reserve

                reserve(self, c, action, event)
            return {"action_id": identity, "state": action["state"]}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.play_confirmed",
                {
                    "channel": channel,
                    "sheet_revision": sheet_revision,
                    "prepared": prepared.model_dump(mode="json"),
                },
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def pending(self, c: Connection, action_id: str) -> list[dict[str, Any]]:
        table = t.m2["m2_choices"]
        return [
            dict(x)
            for x in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.action_id == action_id,
                    table.c.state.in_(("pending", "submitted")),
                )
            ).mappings()
        ]

    def valid_order(
        self, c: Connection, state: GameState, owner: int, channel: int, identity: str | None
    ) -> dict[str, Any]:
        table = t.m2["m2_orders"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.target_id == str(owner),
                    table.c.channel_id == str(channel),
                    table.c.state == "disobey",
                )
            )
            .mappings()
            .first()
        )
        if row is not None and json.loads(row["body_json"]).get("virus_purge"):
            from girlframe.services.m3_virus_orders import valid_order as valid_virus_order

            if valid_virus_order(self, c, state, owner, channel, dict(row)):
                return dict(row)
        if row is not None and json.loads(row["body_json"]).get("npc_order"):
            from girlframe.services.m3_npc_orders import valid_order as valid_npc_order

            if valid_npc_order(self, c, state, owner, channel, dict(row)):
                return dict(row)
        if row is not None and json.loads(row["body_json"]).get("vatgrown_leaving"):
            from girlframe.services.m3_vatgrown_support import valid_departure_order

            if valid_departure_order(self, c, state, dict(row)):
                return dict(row)
        source_authority = False
        if row is not None and json.loads(row["body_json"]).get("am_secret"):
            from girlframe.services.m3_am_scrutinized import valid_pilot_order

            source_authority = valid_pilot_order(self, c, state, dict(row))
        if (
            not source_authority
            and row is not None
            and json.loads(row["body_json"]).get("succubus")
        ):
            from girlframe.services.m3_succubus import valid_order as valid_succubus_order

            source_authority = valid_succubus_order(self, c, state, dict(row))
        if row is not None and json.loads(row["body_json"]).get("gender_designation"):
            from girlframe.services.m3_gender_designation import valid_order as valid_gender_order

            source_authority = valid_gender_order(self, c, state, dict(row)) or source_authority
        if row is not None and json.loads(row["body_json"]).get("stim_sex"):
            from girlframe.services.m3_stim_sex import valid_order as valid_stim_order

            source_authority = valid_stim_order(self, c, state, dict(row)) or source_authority
        if row is not None and json.loads(row["body_json"]).get("bonded"):
            from girlframe.services.m3_bonded import valid_order as valid_bonded_order

            body = json.loads(row["body_json"]) | {"id": row["id"]}
            source_authority = valid_bonded_order(self, c, state, body) or source_authority
        if row is not None and json.loads(row["body_json"]).get("red_queen"):
            from girlframe.engine.m3_actor_state import ActorRef as CourtRef
            from girlframe.services.m3_red_queen import valid_order as valid_court_order

            body = json.loads(row["body_json"]) | {"id": row["id"]}
            target_ref = CourtRef(
                kind="pilot", entity=str(owner), incarnation=state.sheets[str(owner)].character_id
            )
            source_authority = (
                valid_court_order(self, c, state, body, target_ref) or source_authority
            )
        if row is None or (
            not source_authority and not higher(state, int(row["issuer_id"]), owner)
        ):
            raise WorkflowError("A recorded direct order from a current superior is required.")
        if any(
            x.kind == "cannot_refuse_until_tag_resolved"
            and x.state == "pending"
            and x.owner == owner
            and x.target == int(row["issuer_id"])
            for x in state.obligations
        ):
            raise WorkflowError("COMPULSION: resolve the owed Tag before refusing this character.")
        return dict(row)

    def roll(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            original = self.action(c, identity)
        if original["data"].get("leviathan_obsession"):
            from girlframe.services.m3_leviathan_obsession import ObsessionService

            return ObsessionService(self).roll(viewer, key, identity)
        if original["data"].get("virus_purge"):
            from girlframe.services.m3_virus_operations import OperationService

            return OperationService(self).activate(viewer, key, identity)
        if original["data"].get("harpy_defeat"):
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService

            return HarpyDefeatService(self.store, self).roll(viewer, key, identity)

        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            action = self.action(c, identity)
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self).authorize(c, viewer, action)
                return
            if action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(self).authorize(c, viewer, action)
            else:
                self.authorize(c, viewer)
            from girlframe.services.m3_recovery import authorize as authorize_shared

            authorize_shared(self, c, viewer, action)
            if action["data"].get("beneath"):
                from girlframe.services.m3_beneath import authorize as authorize_beneath

                authorize_beneath(self, c, viewer, action)
            if action["data"].get("defeat"):
                from girlframe.services.m3_defeat import authorize as authorize_defeat

                authorize_defeat(self, c, viewer, action)
            if action["data"].get("dive"):
                from girlframe.services.m3_dive import authorize as authorize_dive

                authorize_dive(self, c, viewer, action)
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import authorize as authorize_doctor

                authorize_doctor(self, c, viewer, action)
            if action["data"].get("enforcement"):
                from girlframe.services.m3_enforcement_initiative import (
                    authorize as authorize_enforcement,
                )

                authorize_enforcement(self, c, viewer, action)
            if action["data"].get("am_code"):
                from girlframe.services.m3_am_code import authorize as authorize_am_code

                authorize_am_code(self, c, viewer, action)
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import authorize as authorize_am

                authorize_am(self, c, viewer, action)
            if action["data"].get("alpha_sex"):
                from girlframe.services.m3_alpha_sex import authorize as authorize_alpha_sex

                authorize_alpha_sex(self, c, viewer, action)
            if action["data"].get("alpha"):
                from girlframe.services.m3_alpha import authorize as authorize_alpha

                authorize_alpha(self, c, viewer, action)
            if action["data"].get("npc_order"):
                from girlframe.services.m3_npc_orders import authorize as authorize_npc_order

                authorize_npc_order(self, c, viewer, action)
            if action["data"].get("janus"):
                from girlframe.services.m3_janus_play import authorize as authorize_janus

                authorize_janus(self, c, viewer, action)
            if action["data"].get("snoop"):
                from girlframe.services.m3_enforcer_snoop import authorize as authorize_snoop

                authorize_snoop(self, c, viewer, action)
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import authorize as authorize_battle

                authorize_battle(self, c, viewer, action)

        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            from girlframe.services.m3_princess_sex import authorize_child

            child_actor = authorize_child(
                self, c, viewer, load_state(c, self.store.campaign_id), action
            )
            if child_actor is None and action["actor_id"] != str(viewer.user_id):
                raise WorkflowError("Only the acting Pilot can confirm this roll.")
            if action["data"]["receipt"]:
                return {"action_id": identity, "receipt": action["data"]["receipt"]}
            if action["data"].get("gorgon_play", {}).get("started"):
                return {"action_id": identity, "receipt": None}
            self.unpaused(c)
            if action["data"].get("hidden_sidearm"):
                from girlframe.services.m3_hidden_sidearm import require_clear as sidearm_clear

                sidearm_clear(self, c, load_state(c, self.store.campaign_id), action)
            if action["data"].get("secretary_gunpoint"):
                from girlframe.services.m3_secretary import require_clear as secretary_clear

                secretary_clear(self, c, load_state(c, self.store.campaign_id), action)
            lock = self.lock(c, action["channel_id"])
            if (
                not lock
                or lock["state"] != "held"
                or action["state"] not in ("acquiring", "ready_to_roll")
            ):
                raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no dice or Heat were consumed.")
            if action["data"].get("wyvern_deflected"):
                from girlframe.services.m3_wyvern_combat import require_incoming_response

                require_incoming_response(
                    self, c, load_state(c, self.store.campaign_id), action, "roll"
                )
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                return GorgonPlayService(self).advance(c, viewer, key, action)
            if action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                return ActorPlayService(self).roll(c, viewer, key, action)
            if action["data"].get("adjudication"):
                from girlframe.services.m3_adjudication import reserve_request

                return reserve_request(self, c, viewer, action, key=key)
            if action["data"]["play"] not in (
                *PLAY_IDS,
                *M3_ROLL_IDS,
                *M3_FIXED_IDS,
                *M3_HEAT_IDS,
                *M3_ASSET_IDS,
                *JANUS_ROLL_IDS,
            ):
                raise WorkflowError("This action is diceless.")
            state = load_state(c, self.store.campaign_id)
            self.action_characters(c, action, state)
            if any(x.get("kind") == "fuel_shortage" for x in state.facts):
                from girlframe.services.m3_fuel_shortage import require_complete as fuel_complete
                from girlframe.services.m3_red_queen import _acting as fuel_actor

                fuel_complete(self, c, state, fuel_actor(action))
            from girlframe.services.p1_facilitator import require_scene_clear

            if action["data"].get("bonded_rejection_child"):
                from girlframe.services.m3_bonded_rejection import (
                    pre_roll_child as pre_roll_rejection,
                )

                pre_roll_rejection(self, c, viewer, state, action)
            if action["data"].get("npc_flirt"):
                from girlframe.services.m3_npc_flirt import pre_roll as pre_roll_npc_flirt

                pre_roll_npc_flirt(self, c, viewer, state, action)

            require_scene_clear(self, c, int(action["channel_id"]), action)
            from girlframe.services.p1_source_pause import require_clear as require_source_clear

            require_source_clear(self, c, int(action["channel_id"]), action=action)
            if (
                action["data"].get("prince_mark")
                or action["data"].get("prince_demands")
                or action["data"].get("prince_flirt")
            ):
                from girlframe.services.m3_prince import (
                    flirt_modifier,
                    prepare_demands,
                    prepare_mark,
                )

                saved_inputs = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
                if (
                    prepare_mark(self, c, viewer, state, saved_inputs)
                    != action["data"].get("prince_mark")
                    or prepare_demands(self, c, viewer, state, saved_inputs)
                    != action["data"].get("prince_demands")
                    or flirt_modifier(
                        self, c, viewer, state, saved_inputs, int(action["channel_id"])
                    )
                    != action["data"].get("prince_flirt")
                ):
                    raise WorkflowError(
                        "STALE_FANBASE: reopen the actual demand or audience source before rolling"
                    )
            if action["data"].get("prince"):
                from girlframe.services.m3_prince import pre_roll as pre_roll_prince

                pre_roll_prince(self, c, viewer, state, action)
            if action["data"].get("wyvern_pin_response"):
                from girlframe.services.m3_wyvern_combat import pre_roll_pin_response

                pre_roll_pin_response(self, c, viewer, state, action)
            if action["data"].get("wyvern_replacement"):
                from girlframe.services.m3_wyvern_combat import pre_roll_replacement

                pre_roll_replacement(self, c, viewer, state, action)
            if action["data"].get("wyvern_child"):
                from girlframe.services.m3_wyvern import pre_roll_child as pre_roll_wyvern_child

                pre_roll_wyvern_child(self, c, viewer, state, action)
            from girlframe.services.m3_changeling import pre_roll_flirt
            from girlframe.services.m3_changeling import require_answers as require_psychic_answers
            from girlframe.services.m3_red_queen import _acting as original_roll_actor

            require_psychic_answers(self, c, state, original_roll_actor(action))
            from girlframe.services.m3_ankou import require_source_tasks

            require_source_tasks(self, c, state, action)
            if not action["data"].get("defeat") and not action["data"].get("void_keep"):
                from girlframe.services.m3_ankou import require_free as require_ankou_free

                require_ankou_free(
                    self,
                    c,
                    state,
                    original_roll_actor(action),
                    action["data"].get("ankou_effect_child", {}).get("id"),
                )
            pre_roll_flirt(self, c, state, action)
            if action["data"].get("ankou"):
                from girlframe.services.m3_ankou import pre_roll as pre_roll_ankou

                pre_roll_ankou(self, c, viewer, state, action)
            if action["data"].get("changeling"):
                from girlframe.services.m3_changeling import pre_roll as pre_roll_changeling

                pre_roll_changeling(self, c, viewer, state, action)
            if action["data"].get("changeling_child"):
                from girlframe.services.m3_changeling_effects import (
                    pre_roll_child as pre_roll_changeling_child,
                )

                pre_roll_changeling_child(self, c, viewer, state, action)
            if action["data"].get("red_queen"):
                from girlframe.services.m3_red_queen import pre_roll as pre_roll_red_queen

                pre_roll_red_queen(self, c, viewer, state, action)
            if action["data"].get("princess_child"):
                from girlframe.services.m3_princess_sex import pre_roll_child as pre_roll_princess

                pre_roll_princess(self, c, state, action)
            from girlframe.services.m3_required_plays import pre_roll as pre_roll_required_play

            pre_roll_required_play(self, c, state, action)
            if action["data"].get("ankou_effect_child"):
                from girlframe.services.m3_ankou_feedback_sequences import (
                    pre_roll_child as pre_roll_ankou_effect_child,
                )

                pre_roll_ankou_effect_child(self, c, viewer, state, action)
            if action["data"].get("red_queen_child"):
                from girlframe.services.m3_red_queen_support import (
                    pre_roll_child as pre_roll_royal_child,
                )

                pre_roll_royal_child(self, c, viewer, state, action)
            if action["data"].get("wyvern"):
                from girlframe.services.m3_wyvern import pre_roll as pre_roll_wyvern

                pre_roll_wyvern(self, c, viewer, state, action)
            if action["data"].get("bonded"):
                from girlframe.services.m3_bonded import pre_roll as pre_roll_bonded

                pre_roll_bonded(self, c, viewer, state, action)
            if action["data"].get("bonded_child"):
                from girlframe.services.m3_bonded import pre_roll_child as pre_roll_bonded_child

                pre_roll_bonded_child(self, c, viewer, state, action)
            if action["data"].get("consume"):
                from girlframe.services.m3_consume import pre_roll as pre_roll_consume

                pre_roll_consume(self, c, viewer, state, action)
            if action["data"].get("prince_demand_attempt"):
                from girlframe.services.m3_prince import pre_roll_exception

                pre_roll_exception(self, c, viewer, state, action)
            if action["data"].get("void_keep"):
                from girlframe.services.m3_void_keep import authorize_keep

                authorize_keep(self, c, state, action)
            if HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("STALE_HANDLER: staff recovery is required.")
            from girlframe.services.m3_ankou_feedback import resume_inputs

            committed = resume_inputs(self, c, state, action)
            sheet = state.sheets[str(action["actor_id"])]
            if sheet.revision != action["data"]["sheet_revision"]:
                raise WorkflowError("STALE_SHEET: recover the unrolled action; no dice consumed.")
            prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_nightmare import pre_roll as nightmare_pre_roll

                nightmare_pre_roll(self, c, viewer, state, action, actor=child_actor)
                from girlframe.services.m3_cute_uniforms import pre_roll as cute_pre_roll

                cute_pre_roll(self, c, state, action)
            if action["data"].get("kicked_puppy") is not None or prepared.kicked_puppy_basis:
                from girlframe.services.m3_kicked_puppy import pre_roll as kicked_pre_roll

                kicked_pre_roll(self, c, viewer, state, action)
            if action["data"].get("dampener") is not None or prepared.dampener_modifier is not None:
                from girlframe.services.m3_dampener import pre_roll as dampener_pre_roll

                dampener_pre_roll(self, c, viewer, state, action)
            if action["data"].get("beneath"):
                from girlframe.services.m3_beneath import pre_roll as beneath_pre_roll

                beneath_pre_roll(self, c, viewer, state, action)
            if action["data"].get("dive"):
                from girlframe.services.m3_dive import pre_roll as dive_pre_roll

                dive_pre_roll(self, c, viewer, state, action)
                action["data"]["dive"]["roll_event"] = str(uuid4())
            if action["data"].get("enforcement"):
                from girlframe.services.m3_enforcement_initiative import (
                    pre_roll as enforcement_pre_roll,
                )

                enforcement_pre_roll(self, c, viewer, state, action)
                action["data"]["enforcement"]["roll_event"] = str(uuid4())
            if action["data"].get("oldgen"):
                from girlframe.services.m3_oldgen import pre_roll as pre_roll_oldgen

                pre_roll_oldgen(self, c, viewer, state, action)
            if action["data"].get("vatgrown"):
                from girlframe.services.m3_vatgrown import pre_roll as pre_roll_doll

                pre_roll_doll(self, c, viewer, state, action)
            if action["data"].get("oldgen_sex"):
                from girlframe.services.m3_oldgen_sex import pre_roll as pre_roll_oldgen_sex

                pre_roll_oldgen_sex(self, c, viewer, state, action)
            if action["data"].get("casualty_sex"):
                from girlframe.services.m3_casualty import pre_roll as pre_roll_casualty_sex

                pre_roll_casualty_sex(self, c, viewer, state, action)
            if action["data"].get("vatgrown_sex"):
                from girlframe.services.m3_vatgrown_plays import pre_roll as pre_roll_vatgrown_sex

                pre_roll_vatgrown_sex(self, c, viewer, state, action)
            if action["data"].get("newgirl_sex"):
                from girlframe.services.m3_newgirl_sex import pre_roll as pre_roll_newgirl_sex

                pre_roll_newgirl_sex(self, c, viewer, state, action)
            if action["data"].get("easy_target"):
                from girlframe.services.m3_easy_target import pre_roll as pre_roll_easy_target

                pre_roll_easy_target(self, c, viewer, state, action)
            if action["data"].get("stim_sex"):
                from girlframe.services.m3_stim_sex import pre_roll as pre_roll_stim

                pre_roll_stim(self, c, viewer, state, action)
            if action["data"].get("princess_sex"):
                from girlframe.services.m3_princess_sex import pre_roll as princess_pre_roll

                princess_pre_roll(self, c, viewer, state, action)
            if action["data"].get("dose_up"):
                from girlframe.services.m3_dose_up import pre_roll as dose_pre_roll

                dose_pre_roll(self, c, viewer, state, action)
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import pre_roll as battle_pre_roll

                battle_pre_roll(self, c, state, action)
            if action["data"].get("engage"):
                from girlframe.services.m3_engage import pre_roll as engage_pre_roll

                engage_pre_roll(self, c, state, action)
            if action["data"].get("mockingbird"):
                from girlframe.services.m3_mockingbird_plays import pre_roll as mockingbird_pre_roll

                mockingbird_pre_roll(self, c, state, action)
            if action["data"].get("npc_order"):
                self.valid_order(
                    c, state, int(action["actor_id"]), int(action["channel_id"]), prepared.order_id
                )
            if action["data"].get("learned_keep_rider"):
                from girlframe.services.m3_learned_plays import pre_roll_keep_rider

                pre_roll_keep_rider(self, c, state, action)
            if action["data"].get("learned_no_one_better"):
                from girlframe.services.m3_learned_plays import pre_roll_triggered

                pre_roll_triggered(self, c, state, action)
            if action["data"].get("learned_call"):
                from girlframe.services.m3_learned_plays import pre_roll_call_lesson

                pre_roll_call_lesson(self, c, state, action)
            if action["data"].get("learned_show_dog") or action["data"].get("learned_psyche"):
                from girlframe.services.m3_learned_plays import pre_roll_daily_lessons

                pre_roll_daily_lessons(self, c, state, action)
            from girlframe.services.m3_learned_sex import source_id as learned_sex_id

            if learned_sex_id(action) is not None:
                from girlframe.services.m3_learned_sex import pre_roll as learned_sex_pre_roll

                learned_sex_pre_roll(self, c, state, action)
            if action["data"].get("am_code"):
                from girlframe.services.m3_am_code import pre_roll as pre_roll_am_code

                pre_roll_am_code(self, c, viewer, state, action)
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import pre_roll as pre_roll_am

                pre_roll_am(self, c, viewer, state, action)
            if prepared.play == "disobey_orders":
                from girlframe.engine.m3_actor_bonds import current_ref as am_original
                from girlframe.engine.m3_am import require_freedom

                require_freedom(state, am_original(state, int(action["actor_id"])), "refuse")
            if action["data"].get("alpha_sex"):
                from girlframe.services.m3_alpha_sex import pre_roll as pre_roll_alpha_sex

                pre_roll_alpha_sex(self, c, viewer, state, action)
            if action["data"].get("alpha"):
                from girlframe.services.m3_alpha import pre_roll as alpha_pre_roll

                alpha_pre_roll(self, c, viewer, state, action)
            if action["data"].get("janus"):
                from girlframe.services.m3_janus_play import pre_roll as janus_pre_roll

                janus_pre_roll(self, c, viewer, state, action)
            if action["data"].get("snoop"):
                from girlframe.services.m3_enforcer_snoop import pre_roll as snoop_pre_roll

                snoop_pre_roll(self, c, viewer, state, action)
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import pre_roll as doctor_pre_roll

                action["data"]["doctor"]["roll_event"] = str(uuid4())
                doctor_pre_roll(self, c, viewer, state, action)
                sheet = state.sheets[str(action["actor_id"])]
            m3 = action["data"].get("m3")
            defeat = action["data"].get("defeat")
            if defeat is not None:
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.engine.m3_defeat import modifier as defeat_modifier
                from girlframe.services.m3_actors import profiles

                actual = defeat_modifier(
                    state,
                    ActorRef.model_validate_json(json.dumps(defeat["actor"])),
                    profiles(c, self.store.campaign_id),
                )
                if actual != defeat["modifier"]:
                    raise WorkflowError("STALE_DEFEAT: recover the original unrolled resources.")
                defeat["roll_event"] = str(uuid4())
            if m3 is not None:
                from girlframe.services.m3_play_support import pre_roll

                pre_roll(self, c, viewer, action, state)
            refusal_modifiers = []
            if prepared.play == "disobey_orders":
                from girlframe.services.m3_refusal import pre_roll as consume_refusal

                refusal_modifiers = consume_refusal(self, c, viewer, state, action)
            if committed is None:
                from girlframe.services.m3_ankou_feedback import hold_before_roll

                held_feedback = hold_before_roll(self, c, viewer, state, action, key)
                if held_feedback is not None:
                    return held_feedback
            disposal_before = (
                GameState.model_validate_json(state.model_dump_json())
                if prepared.disposable_heat
                else None
            )
            if committed is None:
                from girlframe.services.m3_disposable_psyche import prepare_disposal

                disposal_permit = prepare_disposal(self, c, state, sheet.owner, prepared)
                if prepared.identity:
                    from girlframe.engine.m3_clone_am import mark_additional
                    from girlframe.services.m3_clone_am import prove_additional

                    prove_additional(self, c, state, sheet.owner, prepared.identity)
                    share = mark_additional(
                        state, sheet, prepared.identity, prepared.gain, prepared.pair_share
                    )
                    if share is None:
                        share = mark_identity(
                            sheet,
                            prepared.identity,
                            prepared.gain,
                            prepared.pair_share,
                            state=state,
                            disposable_heat=prepared.disposable_heat,
                            learned_psyche=disposal_permit,
                        )
                    if share:
                        state.sheets[str(sheet.pair)].heat += share
                        state.sheets[str(sheet.pair)].revision += 1
                if (
                    m3 is None
                    and (
                        not action["data"].get("janus")
                        or action["data"]["janus"].get("mode") == "pandora"
                    )
                    and not prepared.kicked_puppy_basis
                    and not action["data"].get("nightmare_core")
                ):
                    spend_heat(sheet, prepared.heat)

            from girlframe.services.m3_wyvern_support import require_play_target

            require_play_target(self, c, state, prepared)
            from girlframe.services.m3_red_queen import (
                _acting as court_actor,
            )
            from girlframe.services.m3_red_queen import (
                consume_doll,
                doll_source,
            )
            from girlframe.services.m3_red_queen import (
                roll_modifier as court_modifier,
            )

            court_event = next(
                (
                    action["data"][name]["roll_event"]
                    for name in ("defeat", "doctor", "dive", "enforcement", "battle", "janus")
                    if action["data"].get(name, {}).get("roll_event")
                ),
                str(uuid4()),
            )
            if prepared.ankou_pulse:
                from girlframe.engine.m3_actor_state import ActorRef as PulseTarget
                from girlframe.services.m3_ankou import apply_pulse

                pulse_target = prepared.target_actor
                if pulse_target is None and prepared.target is not None:
                    original_id = action["data"].get("character_ids", {}).get(str(prepared.target))
                    if original_id:
                        pulse_target = PulseTarget(
                            kind="pilot", entity=str(prepared.target), incarnation=original_id
                        )
                if pulse_target is None:
                    raise WorkflowError("Choose this actual Play's original Amygdala target")
                apply_pulse(self, c, state, action, prepared.ankou_pulse, pulse_target, court_event)
                action["data"]["ankou_pulse"] = prepared.ankou_pulse
            court_adjustment = court_modifier(self, c, state, action, court_event)
            from girlframe.services.m3_ankou import (
                consume_roll_modifiers as consume_ankou_modifiers,
            )

            ankou_modifiers = consume_ankou_modifiers(self, c, state, action, court_event)
            if ankou_modifiers:
                action["data"]["ankou_roll_modifiers"] = ankou_modifiers
            from girlframe.services.m3_changeling import (
                consume_flirt,
            )
            from girlframe.services.m3_changeling import (
                flirt_modifier as psychic_flirt_modifier,
            )

            psychic_flirt = psychic_flirt_modifier(self, c, state, action)
            if psychic_flirt:
                consume_flirt(self, c, state, action, court_event)
            court_doll = (
                doll_source(self, c, state, court_actor(action))
                if prepared.play == "disobey_orders"
                else None
            )
            if court_doll is not None:
                consume_doll(self, c, state, court_doll["id"], action["id"], court_event)
                action["data"]["red_queen_doll"] = court_doll
            if court_adjustment:
                action["data"]["red_queen_modifier"] = court_adjustment
            entry_modifiers = []
            if action["data"].get("void_frame_entry"):
                from girlframe.services.m3_void_frame_entry import pre_roll as entry_pre_roll

                entry_modifiers = entry_pre_roll(self, c, state, action, court_event)
            faces = self.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise ValueError("Dice source returned invalid faces")
            pre_modifiers = (
                [
                    {"source": x["source"], "amount": x["amount"]}
                    for x in m3.get("pre_modifiers", [])
                ]
                if m3
                else []
            )
            pre_modifiers += refusal_modifiers
            pre_modifiers.extend(ankou_modifiers)
            pre_modifiers.extend(entry_modifiers)
            if psychic_flirt:
                pre_modifiers.append(dict(source="changeling_fingers_flirt", amount=psychic_flirt))
            if court_adjustment:
                pre_modifiers.append(dict(source="red_queen_personality", amount=court_adjustment))
            from girlframe.services.m3_consume import acting as consume_actor
            from girlframe.services.p1_consume_hooks import roll_modifiers as consume_modifiers

            consuming_actor = consume_actor(state, action)
            if consuming_actor is not None and not action["data"].get("wyvern_pin_response"):
                from girlframe.services.m3_wyvern_combat import require_free

                require_free(self, c, state, consuming_actor)
            if consuming_actor is not None:
                pre_modifiers.extend(consume_modifiers(self, c, state, consuming_actor, prepared))
                from girlframe.services.m3_wyvern_support import wraith_modifiers

                pre_modifiers.extend(
                    wraith_modifiers(self, c, state, consuming_actor, prepared.play)
                )
            if action["data"].get("prince_flirt"):
                pre_modifiers.append({"source": "prince_power_imbalance", "amount": 2})
            if action["data"].get("consume") and action["data"]["consume"].get("basis") is not None:
                pre_modifiers.append(
                    {
                        "source": "consume_source_basis",
                        "amount": action["data"]["consume"]["basis"] - prepared.heat,
                    }
                )
            from girlframe.services.m3_special_girl import modifiers as special_girl_modifiers

            pre_modifiers += special_girl_modifiers(action)
            if action["data"].get("janus") and action["data"]["janus"].get("mode") != "pandora":
                pre_modifiers.append(
                    dict(source="battery_tags", amount=len(action["data"]["janus"]["tags"]))
                )
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import modifier as battle_modifier

                pre_modifiers.append(
                    dict(source="core_intact_assets", amount=battle_modifier(state, action))
                )
            receipt = {
                "id": str(uuid4()),
                "action_id": identity,
                "faces": list(faces),
                "heat": prepared.heat,
                "pre_total": sum(faces)
                + (
                    m3["modifier"]
                    if m3 is not None
                    else defeat["modifier"]
                    if defeat is not None
                    else action["data"]["nightmare_core"]["modifier"]
                    if action["data"].get("nightmare_core")
                    else action["data"]["kicked_puppy"]["modifier"]
                    if prepared.kicked_puppy_basis
                    else action["data"]["dampener"]["modifier"]
                    if action["data"].get("dampener")
                    else prepared.heat
                )
                + sum(x["amount"] for x in pre_modifiers),
                "rng_source": self.rng_source,
                "rolled_utc": datetime.now(UTC).isoformat(),
                "ruleset": M3_RULESET
                if m3 is not None
                or refusal_modifiers
                or action["data"].get("beneath")
                or action["data"].get("doctor")
                or action["data"].get("dive")
                or action["data"].get("void_keep")
                or action["data"].get("enforcement")
                or action["data"].get("battle")
                or action["data"].get("engage")
                or action["data"].get("mockingbird")
                or action["data"].get("snoop")
                or action["data"].get("janus")
                or action["data"].get("alpha")
                or action["data"].get("alpha_sex")
                or action["data"].get("dose_up")
                or action["data"].get("princess_sex")
                or action["data"].get("stim_sex")
                or action["data"].get("oldgen_sex")
                or action["data"].get("casualty_sex")
                or action["data"].get("vatgrown_sex")
                or action["data"].get("prince")
                or action["data"].get("prince_mark")
                or action["data"].get("prince_demands")
                or action["data"].get("prince_flirt")
                or action["data"].get("prince_override")
                or action["data"].get("consume")
                or action["data"].get("prince_demand_attempt")
                or action["data"].get("consume_child")
                or action["data"].get("bonded")
                or action["data"].get("wyvern")
                or action["data"].get("red_queen")
                or action["data"].get("changeling")
                or action["data"].get("ankou")
                or action["data"].get("bonded_child")
                or action["data"].get("wyvern_child")
                or action["data"].get("red_queen_child")
                or action["data"].get("ankou_effect_child")
                or action["data"].get("changeling_child")
                or action["data"].get("wyvern_pin_response")
                or action["data"].get("wyvern_replacement")
                or action["data"].get("newgirl_sex")
                or action["data"].get("easy_target")
                or action["data"].get("easy_target_child")
                or action["data"].get("vatgrown")
                or action["data"].get("oldgen")
                or action["data"].get("princess_child")
                or action["data"].get("ankou_feedback")
                or action["data"].get("ankou_feedback_child")
                or prepared.disposable_heat
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
                or action["data"].get("npc_flirt")
                or action["data"].get("bonded_rejection_child")
                or action["data"].get("dampener")
                or action["data"].get("kicked_puppy")
                or action["data"].get("nightmare_core")
                or action["data"].get("cute_uniforms")
                or action["data"].get("cute_uniform_tags")
                or action["data"].get("cute_uniform_rejection")
                or defeat is not None
                else RULESET,
            }
            if m3 is not None:
                receipt.update(
                    pre_modifiers=pre_modifiers,
                    base_modifier=m3["modifier"],
                    modifier_source="Void Assets"
                    if m3.get("modifier_source") == "void_assets"
                    else "Status",
                )
            elif defeat is not None:
                receipt.update(
                    base_modifier=defeat["modifier"],
                    modifier_source="Undamaged Girl Assets",
                    pre_modifiers=[],
                )
            elif action["data"].get("janus"):
                receipt.update(
                    pre_modifiers=pre_modifiers,
                    base_modifier=prepared.heat
                    if action["data"]["janus"].get("mode") == "pandora"
                    else 0,
                    modifier_source="Heat"
                    if action["data"]["janus"].get("mode") == "pandora"
                    else "Battery Tags",
                )
            elif refusal_modifiers:
                receipt.update(
                    pre_modifiers=pre_modifiers, base_modifier=prepared.heat, modifier_source="Heat"
                )
            if (
                court_adjustment or psychic_flirt or ankou_modifiers or entry_modifiers
            ) and "pre_modifiers" not in receipt:
                receipt.update(
                    pre_modifiers=pre_modifiers, base_modifier=prepared.heat, modifier_source="Heat"
                )
            if action["data"].get("dose_up"):
                receipt.update(
                    pre_modifiers=pre_modifiers, base_modifier=prepared.heat, modifier_source="Heat"
                )
            if action["data"].get("dampener"):
                receipt.update(
                    pre_modifiers=pre_modifiers,
                    base_modifier=action["data"]["dampener"]["modifier"],
                    modifier_source="Dampener Link",
                    dampener_purchase=action["data"]["dampener"]["purchase"],
                )
            if action["data"].get("kicked_puppy"):
                receipt["kicked_purchase"] = action["data"]["kicked_puppy"]["purchase"]
                if prepared.kicked_puppy_basis:
                    receipt.update(
                        pre_modifiers=pre_modifiers,
                        base_modifier=action["data"]["kicked_puppy"]["modifier"],
                        modifier_source="Damaged Girl Assets (Kicked Puppy)",
                        kicked_basis=True,
                    )
            if action["data"].get("nightmare_core"):
                receipt.update(
                    pre_modifiers=pre_modifiers,
                    base_modifier=action["data"]["nightmare_core"]["modifier"],
                    modifier_source="Void Assets (Nightmare Core)",
                    nightmare_purchase=action["data"]["nightmare_core"]["purchase"],
                )
            from girlframe.services.m3_special_girl import receipt as special_girl_receipt

            special_girl_receipt(action, receipt, pre_modifiers)
            roll_event_id = (
                defeat["roll_event"]
                if defeat is not None
                else action["data"]["doctor"]["roll_event"]
                if action["data"].get("doctor")
                else action["data"]["dive"]["roll_event"]
                if action["data"].get("dive")
                else action["data"]["enforcement"]["roll_event"]
                if action["data"].get("enforcement")
                else action["data"]["battle"]["roll_event"]
                if action["data"].get("battle")
                else action["data"]["janus"]["roll_event"]
                if action["data"].get("janus")
                else None
            )
            from girlframe.engine.m3_red_queen import Mark as CourtMark
            from girlframe.engine.m3_red_queen import records as court_records

            if (
                psychic_flirt
                or court_doll is not None
                or any(
                    x.used_action == action["id"] and x.applied_event == court_event
                    for x in court_records(state, CourtMark)
                )
            ):
                roll_event_id = court_event
            if committed is not None:
                roll_event_id = roll_event_id or str(uuid4())
            if disposal_before is not None:
                from girlframe.services.m3_disposable_psyche import record_disposal

                roll_event_id = roll_event_id or str(uuid4())
                receipt["disposable_psyche"] = identity
                action["data"]["receipt"] = receipt
                record_disposal(self, c, state, action, disposal_before, roll_event_id)
            c.execute(
                t.m2["m2_receipts"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    action_id=identity,
                    id=receipt["id"],
                    body_json=json.dumps(receipt, sort_keys=True),
                )
            )
            action["data"]["receipt"] = receipt
            sheet.revision += 1
            self.save_action(c, action, state="tag_window")
            for person in action["data"]["participants"]:
                self.request(c, action, person, "tag_window")
            self.queue(
                c,
                action,
                "receipt",
                {"receipt": receipt, "callsign": sheet.callsign, "play": prepared.play},
            )
            from girlframe.engine.m3_actor_state import ActorRef as DollActRef
            from girlframe.engine.m3_vatgrown import stage_act as stage_doll_act

            doll_source_actor = action["data"].get("tag_context", {}).get("actor")
            doll_original_character = (
                action["data"].get("character_ids", {}).get(str(action["actor_id"]))
            )
            doll_act_actor = (
                DollActRef.model_validate_json(json.dumps(doll_source_actor))
                if doll_source_actor is not None
                else DollActRef(
                    kind="pilot",
                    entity=str(action["actor_id"]),
                    incarnation=doll_original_character,
                )
                if doll_original_character is not None
                else None
            )
            if doll_act_actor is not None:
                doll_act_event = roll_event_id or str(uuid4())
                if stage_doll_act(
                    state,
                    doll_act_actor,
                    action["scene_id"],
                    action["id"],
                    doll_act_event,
                    "play",
                ):
                    roll_event_id = doll_act_event
            if action["data"].get("prince_mark") or action["data"].get("prince_demands"):
                from girlframe.services.m3_prince import record_mark

                roll_event_id = roll_event_id or str(uuid4())
                record_mark(self, c, state, action, roll_event_id)
            if action["data"].get("learned_play"):
                from girlframe.services.m3_learned_plays import consume as consume_learned_play

                roll_event_id = roll_event_id or str(uuid4())
                consume_learned_play(self, c, state, action, roll_event_id)
            if action["data"].get("learned_keep_rider"):
                from girlframe.services.m3_learned_plays import consume_keep_rider

                roll_event_id = roll_event_id or str(uuid4())
                consume_keep_rider(self, c, state, action, roll_event_id)
                if action["data"]["play"] == "keep_your_head":
                    self.save_action(c, action)
            if action["data"].get("learned_show_dog") or action["data"].get("learned_psyche"):
                from girlframe.services.m3_learned_plays import consume_daily_lessons

                roll_event_id = roll_event_id or str(uuid4())
                consume_daily_lessons(self, c, state, action, roll_event_id)
                action["data"]["sheet_revision"] = state.sheets[str(action["actor_id"])].revision
                self.save_action(c, action)
            from girlframe.services.m3_learned_sex import source_id as learned_sex_id

            if learned_sex_id(action) is not None:
                from girlframe.services.m3_learned_sex import consume as consume_learned_sex

                roll_event_id = roll_event_id or str(uuid4())
                consume_learned_sex(self, c, state, action, roll_event_id)
                action["data"]["sheet_revision"] = state.sheets[str(action["actor_id"])].revision
                self.save_action(c, action)
            if committed is not None:
                from girlframe.services.m3_ankou_feedback import record_roll

                assert roll_event_id is not None
                record_roll(self, c, state, action, roll_event_id, receipt)
            event = self.event(
                c,
                viewer.user_id,
                key,
                "m3.rolled"
                if m3 is not None
                or refusal_modifiers
                or action["data"].get("beneath")
                or action["data"].get("doctor")
                or action["data"].get("enforcement")
                or action["data"].get("battle")
                or action["data"].get("engage")
                or action["data"].get("mockingbird")
                or action["data"].get("snoop")
                or action["data"].get("janus")
                or action["data"].get("alpha")
                or action["data"].get("alpha_sex")
                or action["data"].get("dose_up")
                or action["data"].get("princess_sex")
                or action["data"].get("stim_sex")
                or action["data"].get("oldgen_sex")
                or action["data"].get("casualty_sex")
                or action["data"].get("vatgrown_sex")
                or action["data"].get("prince")
                or action["data"].get("prince_mark")
                or action["data"].get("prince_demands")
                or action["data"].get("prince_flirt")
                or action["data"].get("prince_override")
                or action["data"].get("consume")
                or action["data"].get("prince_demand_attempt")
                or action["data"].get("consume_child")
                or action["data"].get("bonded")
                or action["data"].get("wyvern")
                or action["data"].get("red_queen")
                or action["data"].get("changeling")
                or action["data"].get("ankou")
                or action["data"].get("bonded_child")
                or action["data"].get("wyvern_child")
                or action["data"].get("red_queen_child")
                or action["data"].get("ankou_effect_child")
                or action["data"].get("changeling_child")
                or action["data"].get("wyvern_pin_response")
                or action["data"].get("wyvern_replacement")
                or action["data"].get("newgirl_sex")
                or action["data"].get("easy_target")
                or action["data"].get("easy_target_child")
                or action["data"].get("vatgrown")
                or action["data"].get("oldgen")
                or action["data"].get("princess_child")
                or action["data"].get("ankou_feedback")
                or action["data"].get("ankou_feedback_child")
                or prepared.disposable_heat
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
                or action["data"].get("npc_flirt")
                or action["data"].get("bonded_rejection_child")
                or action["data"].get("dampener")
                or action["data"].get("kicked_puppy")
                or action["data"].get("nightmare_core")
                or action["data"].get("cute_uniforms")
                or action["data"].get("cute_uniform_tags")
                or action["data"].get("cute_uniform_rejection")
                or defeat is not None
                else "m2.rolled",
                state,
                event_id=roll_event_id,
                action_id=identity,
                receipt_id=receipt["id"],
            )
            if m3 is not None:
                from girlframe.services.m3_play_support import save_raw_roll

                save_raw_roll(self, c, action, state, event)
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import synchronize as synchronize_doctor

                synchronize_doctor(self, c, action, event)
            if action["data"].get("changeling_remote"):
                from girlframe.services.m3_changeling_sex import (
                    synchronize_action as sync_remote_source,
                )

                sync_remote_source(self, c, self.action(c, action["id"]), event)
            return {"action_id": identity, "receipt": receipt}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.rolled",
                {"action_id": identity},
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def pending_choices(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        """Original row owners, with only the proven Princess child's scoped author."""
        table, actions = t.m2["m2_choices"], t.m2["m2_actions"]
        rows = c.execute(
            sa.select(table)
            .join(
                actions,
                sa.and_(
                    actions.c.campaign_id == table.c.campaign_id, actions.c.id == table.c.action_id
                ),
            )
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.state == "pending",
                sa.or_(
                    table.c.actor_id == str(viewer.user_id),
                    sa.func.json_extract(actions.c.body_json, "$.princess_child.author")
                    == viewer.user_id,
                ),
            )
        ).mappings()
        from girlframe.services.m3_princess_sex import decision_author

        state = load_state(c, self.store.campaign_id)
        result = []
        for row in rows:
            action = self.action(c, row["action_id"])
            source_author = decision_author(self, c, state, action, dict(row))
            if viewer.user_id == (
                source_author if source_author is not None else int(row["actor_id"])
            ):
                result.append(dict(row))
        return result

    def choices(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            return self.pending_choices(c, viewer)

    def respond(
        self, viewer: GuildViewer, key: str, choice_id: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        from girlframe.services.m2_choices import ChoiceEngine

        answer = ChoiceAnswer.model_validate_json(answer.model_dump_json())
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            choices = t.m2["m2_choices"]
            original = c.execute(
                sa.select(choices.c.action_id, choices.c.kind).where(
                    choices.c.campaign_id == self.store.campaign_id,
                    choices.c.id == choice_id,
                    choices.c.actor_id == str(viewer.user_id),
                )
            ).first()
            if original and original.kind == "battle_sprite_intercept":
                raise WorkflowError(
                    "Use your actual Sprite interception controls; a generic response cannot choose"
                )
            leviathan = bool(
                original and self.action(c, original.action_id)["data"].get("leviathan_obsession")
            )
            virus_order = bool(
                original and self.action(c, original.action_id)["data"].get("virus_order")
            )
            virus_purge = bool(
                original and self.action(c, original.action_id)["data"].get("virus_purge")
            )
            harpy_defeat = bool(
                original and self.action(c, original.action_id)["data"].get("harpy_defeat")
            )
        if leviathan:
            from girlframe.services.m3_leviathan_obsession import ObsessionService

            return ObsessionService(self).respond(viewer, key, choice_id, revision, answer)
        if virus_purge and not virus_order:
            raise WorkflowError(
                "Use actual source purge/Punishment controls; "
                "generic acknowledgement cannot finish it."
            )
        if virus_order:
            from girlframe.services.m3_virus_orders import VirusOrderService

            return VirusOrderService(self).respond(viewer, key, choice_id, revision, answer)
        if harpy_defeat:
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService

            return HarpyDefeatService(self.store, self).respond(
                viewer, key, choice_id, revision, answer
            )

        def owned(c: Connection) -> dict[str, Any]:
            self.authorize(c, viewer, game=False)
            table = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == choice_id,
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision belongs to another player or is unavailable.")
            action = self.action(c, row["action_id"])
            from girlframe.services.m3_princess_sex import decision_author

            scoped_author = decision_author(
                self, c, load_state(c, self.store.campaign_id), action, dict(row)
            )
            if viewer.user_id != (
                scoped_author if scoped_author is not None else int(row["actor_id"])
            ):
                raise WorkflowError("This decision belongs to another player or is unavailable.")
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self).authorize(c, viewer, action)
                return dict(row)
            if row["kind"] == "budget_asset_calamity":
                from girlframe.services.m3_access import Access

                Access(self.store).authorize(c, viewer, "strain")
            director_tag_response = False
            if action["data"].get("npc_flirt"):
                from girlframe.services.m3_npc_flirt import authorize as authorize_npc_flirt

                authorize_npc_flirt(self, c, viewer, action)
                return dict(row)
            if row["kind"] == "prince_bad_girl":
                from girlframe.services.m3_access import Access

                gate = Access(self.store)
                gate.authorize(c, viewer, "plays", director_response=True)
                assert gate.registry is not None
                gate.registry.require_available("frame.prince.bad-girl")
                return dict(row)
            if action["data"].get("prince"):
                from girlframe.services.m3_prince import authorize as authorize_prince

                authorize_prince(self, c, viewer, action)
                return dict(row)
            if action["data"].get("ankou"):
                from girlframe.services.m3_ankou import authorize as authorize_ankou

                authorize_ankou(self, c, viewer, action)
            if action["data"].get("changeling"):
                from girlframe.services.m3_changeling import authorize as authorize_changeling

                authorize_changeling(self, c, viewer, action)
            if action["data"].get("red_queen"):
                from girlframe.services.m3_red_queen import authorize as authorize_red_queen

                authorize_red_queen(self, c, viewer, action)
            if action["data"].get("wyvern"):
                from girlframe.services.m3_wyvern import authorize as authorize_wyvern

                authorize_wyvern(self, c, viewer, action)
            if action["data"].get("bonded"):
                from girlframe.services.m3_bonded import authorize as authorize_bonded

                authorize_bonded(self, c, viewer, action)
            if action["data"].get("consume") or row["kind"].startswith("consume_"):
                from girlframe.services.m3_consume import authorize as authorize_consume

                authorize_consume(self, c, viewer, action)
                return dict(row)
            if row["kind"] == "casualty_roll_push":
                from girlframe.services.m3_access import Access

                gate = Access(self.store)
                gate.authorize(c, viewer, "plays")
                assert gate.registry is not None
                gate.registry.require_available("girl.casualty.wounded-god")
                return dict(row)
            if action["data"].get("vatgrown"):
                from girlframe.services.m3_vatgrown import authorize as doll_authorize

                doll_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("oldgen_sex"):
                from girlframe.services.m3_oldgen_sex import authorize as oldgen_sex_authorize

                oldgen_sex_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("casualty_sex"):
                from girlframe.services.m3_casualty import authorize as casualty_sex_authorize

                casualty_sex_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("vatgrown_sex"):
                from girlframe.services.m3_vatgrown_plays import authorize as vatgrown_sex_authorize

                vatgrown_sex_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("newgirl_sex"):
                from girlframe.services.m3_newgirl_sex import authorize as newgirl_sex_authorize

                newgirl_sex_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("easy_target"):
                from girlframe.services.m3_easy_target import authorize as easy_target_authorize

                easy_target_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("stim_sex"):
                from girlframe.services.m3_stim_sex import authorize as stim_authorize

                stim_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("princess_sex"):
                from girlframe.services.m3_princess_sex import authorize as princess_authorize

                princess_authorize(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import authorize as authorize_doctor

                authorize_doctor(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("am_code"):
                from girlframe.services.m3_am_code import authorize as authorize_am_code

                authorize_am_code(self, c, viewer, action)
                director_tag_response = True
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import authorize as authorize_am

                authorize_am(self, c, viewer, action)
                director_tag_response = True
            elif action["data"].get("alpha_sex"):
                from girlframe.services.m3_alpha_sex import authorize as authorize_alpha_sex

                authorize_alpha_sex(self, c, viewer, action)
                director_tag_response = True
            elif action["data"].get("npc_order"):
                from girlframe.services.m3_npc_orders import authorize as authorize_npc_order

                authorize_npc_order(self, c, viewer, action)
                director_tag_response = True
            elif action["data"].get("alpha"):
                from girlframe.services.m3_alpha import authorize as authorize_alpha

                authorize_alpha(self, c, viewer, action)
                if viewer.user_id not in action["data"]["alpha"]["table"]:
                    raise WorkflowError("Only the original Alpha source table owns this response")
                director_tag_response = True
            elif action["data"].get("janus"):
                from girlframe.services.m3_janus_play import authorize as authorize_janus

                authorize_janus(self, c, viewer, action)
                meta = action["data"]["janus"]
                if viewer.user_id not in {*meta["table"], meta["target_controller"]}:
                    raise WorkflowError("Only this original neural-link table owns its responses")
                director_tag_response = True
            elif action["data"].get("snoop"):
                from girlframe.services.m3_enforcer_snoop import authorize as authorize_snoop

                authorize_snoop(self, c, viewer, action)
                meta = action["data"]["snoop"]
                if viewer.user_id not in {
                    *meta["table"],
                    meta["target_controller"],
                    meta["procedural_gm"],
                }:
                    raise WorkflowError(
                        "Only the original source participants own this Snoop response"
                    )
                director_tag_response = True
            elif action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(self).authorize(c, viewer, action)
            elif action["data"].get("battle"):
                from girlframe.services.m3_battle import authorize as authorize_battle

                authorize_battle(self, c, viewer, action)
                if viewer.user_id not in action["data"]["participants"]:
                    raise WorkflowError(
                        "Only an original source-table human owns this battle response."
                    )
                director_tag_response = True
            elif action["data"].get("mockingbird") and row["kind"].startswith("mockingbird_"):
                from girlframe.services.m3_mockingbird_plays import authorize_response

                authorize_response(self, c, viewer, action)
                director_tag_response = True
            elif action["data"].get("dive") and row["kind"].startswith("dive_"):
                from girlframe.services.m3_dive import authorize as authorize_dive

                authorize_dive(self, c, viewer, action)
                if viewer.user_id not in action["data"]["dive"]["table"]:
                    raise WorkflowError(
                        "Only the original source-table human owns this Dive response"
                    )
                director_tag_response = True
            elif row["kind"] in (
                "tag_window",
                "tag_marker_selection",
                "tag_marker_agreement",
            ) and any(
                context.active and context.handler == viewer.user_id
                for context in load_state(c, self.store.campaign_id).director_contexts
            ):
                # A current Director may exercise this same original body's printed
                # other-player Tag role; this grants no new Pilot or Handler Play.
                self.gate()
                from girlframe.services.m3_tag_markers import current as current_markers

                current_markers(
                    self, c, load_state(c, self.store.campaign_id), action, viewer.user_id
                )
                director_tag_response = True
            else:
                self.authorize(c, viewer)
            if action["data"].get("m3"):
                from girlframe.services.m3_play_support import authorize as authorize_m3

                authorize_m3(self, c, viewer, action)
            from girlframe.services.m3_recovery import authorize as authorize_shared

            authorize_shared(self, c, viewer, action, director_response=director_tag_response)
            procedural_handler = (action["data"].get("battle") or {}).get(
                "procedural_gm", action["data"]["handler"]
            )
            if (
                str(viewer.user_id) == str(procedural_handler)
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError("The Handler appointment changed; staff recovery is required.")
            if row["kind"] == "reign_group_tag_resolution":
                from girlframe.services.m3_reign_terror import ReignTerrorService

                ReignTerrorService(self.store)._access(c, viewer)
            if row["kind"] == "sidearm_reconsider":
                from girlframe.services.m3_hidden_sidearm import HiddenSidearmService

                HiddenSidearmService(self.store)._access(c, viewer)
            if row["kind"] in (
                "secretary_gunpoint",
                "secretary_response_play",
                "secretary_gunpoint_resolution",
            ):
                from girlframe.services.m3_secretary import SecretaryService

                SecretaryService(self.store)._access(c, viewer)
            if action["data"].get("beneath"):
                from girlframe.services.m3_beneath import authorize as authorize_beneath

                authorize_beneath(self, c, viewer, action)
            if action["data"].get("dive"):
                from girlframe.services.m3_dive import authorize as authorize_dive

                authorize_dive(self, c, viewer, action)
            if action["data"].get("enforcement"):
                from girlframe.services.m3_enforcement_initiative import (
                    authorize as authorize_enforcement,
                )

                authorize_enforcement(self, c, viewer, action)
            return dict(row)

        def authorize(c: Connection) -> None:
            owned(c)

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            row = owned(c)
            if row["state"] != "pending" or row["revision"] != revision:
                raise WorkflowError("STALE_CHOICE: reopen your current decisions.")
            action = self.action(c, row["action_id"])
            if action["state"] in ("complete", "aborted"):
                raise WorkflowError("This action no longer accepts decisions.")
            lock = self.lock(c, action["channel_id"])
            if not lock or lock["state"] != "held":
                raise WorkflowError("SCENE_LOCK_RECOVERY: decisions await a confirmed scene lock.")
            state = load_state(c, self.store.campaign_id)
            if action["data"].get("wyvern_deflected"):
                from girlframe.services.m3_wyvern_combat import require_incoming_response

                require_incoming_response(self, c, state, action, row["kind"])
            if not action["data"].get("actor_basic") and not action["data"].get("gorgon_play"):
                from girlframe.services.m3_battle_dormant import proved_converted_originals

                self.action_characters(
                    c,
                    action,
                    state,
                    allowed_archived=proved_converted_originals(self, c, state, action),
                )
            if action["data"]["play"] == "disobey_orders":
                from girlframe.engine.m3_control_ritual import rituals
                from girlframe.services.m3_access import Access

                if rituals(state):
                    Access(self.store).authorize(c, viewer, "strain")
            from girlframe.services.p1_facilitator import require_scene_clear

            require_scene_clear(self, c, int(action["channel_id"]), action)
            from girlframe.services.p1_source_pause import require_clear as require_source_clear

            require_source_clear(self, c, int(action["channel_id"]), action=action)
            table = t.m2["m2_choices"]
            c.execute(
                table.update()
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == choice_id)
                .values(state="answered", revision=revision + 1)
            )
            action["data"]["choices"][row["kind"] + ":" + row["actor_id"]] = answer.model_dump(
                mode="json"
            )
            action["data"]["response_event"] = str(uuid4())
            if action["data"].get("void_keep") and not action["data"]["void_keep"].get(
                "resistance_resolved"
            ):
                from girlframe.services.m3_void_keep import authorize_keep

                authorize_keep(self, c, state, action)
            if action["data"].get("defeat"):
                from girlframe.services.m3_defeat import authorize as authorize_defeat

                authorize_defeat(self, c, viewer, action)
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self).apply(c, state, action, row, answer)
            elif action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(self).apply(c, state, action, row, answer, viewer=viewer)
            else:
                ChoiceEngine(self).apply(c, state, action, row, answer)
            self.save_action(c, action)
            if action["data"].get("play") == "go_off_duty" and action["state"] == "complete":
                from girlframe.services.m3_prince import sync_off_duty as sync_prince_off_duty

                sync_prince_off_duty(self, c, state, action)
            event = self.event(
                c,
                viewer.user_id,
                key,
                "m3.choice_resolved"
                if action["data"].get("m3")
                or action["data"].get("dampener")
                or action["data"].get("kicked_puppy")
                or action["data"].get("nightmare_core")
                or action["data"].get("cute_uniforms")
                or action["data"].get("cute_uniform_tags")
                or action["data"].get("cute_uniform_rejection")
                or action["data"].get("actor_basic")
                or action["data"].get("beneath")
                or action["data"].get("doctor")
                or action["data"].get("defeat")
                or action["data"].get("dive")
                or action["data"].get("void_keep")
                or action["data"].get("enforcement")
                or action["data"].get("handler_play_m3")
                or action["data"].get("battle")
                or action["data"].get("engage")
                or action["data"].get("mockingbird")
                or action["data"].get("snoop")
                or action["data"].get("janus")
                or action["data"].get("alpha")
                or action["data"].get("alpha_sex")
                or action["data"].get("dose_up")
                or action["data"].get("princess_sex")
                or action["data"].get("stim_sex")
                or action["data"].get("oldgen_sex")
                or action["data"].get("casualty_sex")
                or action["data"].get("vatgrown_sex")
                or action["data"].get("prince")
                or action["data"].get("prince_mark")
                or action["data"].get("prince_demands")
                or action["data"].get("prince_flirt")
                or action["data"].get("prince_override")
                or action["data"].get("consume")
                or action["data"].get("prince_demand_attempt")
                or action["data"].get("consume_child")
                or action["data"].get("bonded")
                or action["data"].get("wyvern")
                or action["data"].get("red_queen")
                or action["data"].get("changeling")
                or action["data"].get("ankou")
                or action["data"].get("bonded_child")
                or action["data"].get("wyvern_child")
                or action["data"].get("red_queen_child")
                or action["data"].get("ankou_effect_child")
                or action["data"].get("changeling_child")
                or action["data"].get("wyvern_pin_response")
                or action["data"].get("wyvern_replacement")
                or action["data"].get("newgirl_sex")
                or action["data"].get("easy_target")
                or action["data"].get("easy_target_child")
                or action["data"].get("vatgrown")
                or action["data"].get("oldgen")
                or action["data"].get("princess_child")
                or action["data"].get("ankou_feedback")
                or action["data"].get("ankou_feedback_child")
                or (action["data"].get("receipt") or {}).get("disposable_psyche")
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
                or action["data"].get("npc_flirt")
                or action["data"].get("bonded_rejection_child")
                or action["data"].get("gorgon_play")
                else "m2.choice_resolved",
                state,
                event_id=action["data"]["response_event"],
                action_id=action["id"],
                choice_id=choice_id,
            )
            if row["kind"] == "order_response":
                from girlframe.services.m3_gender_designation import synchronize_no

                synchronize_no(self, c, action, event)
            if action["data"].get("cute_uniform_rejection"):
                from girlframe.services.m3_cute_uniforms import synchronize_rejection

                synchronize_rejection(self, c, action, event)
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self).synchronize(c, action, event, viewer, key)
                action = self.action(c, action["id"])
            if action["data"].get("mockingbird"):
                from girlframe.services.m3_mockingbird_plays import (
                    synchronize as synchronize_mock_play,
                )

                synchronize_mock_play(self, c, action, event)
            if action["data"].get("risk_factor"):
                from girlframe.services.m3_mockingbird import synchronize as synchronize_mockingbird

                synchronize_mockingbird(self, c, action, event)
            if action["data"].get("m3_finished"):
                from girlframe.services.m3_play_support import sync_finished_roll

                sync_finished_roll(self, c, action, event)
                if action["data"].get("risk_factor"):
                    action["data"]["risk_factor"]["period_roll_synced"] = event
                    self.save_action(c, action)
            if action["data"].get("beneath"):
                from girlframe.services.m3_beneath import synchronize as synchronize_beneath

                synchronize_beneath(self, c, action, event)
            if action["data"].get("defeat"):
                from girlframe.services.m3_defeat import synchronize as synchronize_defeat

                synchronize_defeat(self, c, action, event, viewer, key)
            if action["data"].get("clone_flirt"):
                from girlframe.services.m3_clone_am_plays import synchronize as synchronize_clone

                synchronize_clone(self, c, action, event)
            if action["data"].get("dive"):
                from girlframe.services.m3_dive import synchronize as synchronize_dive

                synchronize_dive(self, c, action, event)
            if action["data"].get("enforcement"):
                from girlframe.services.m3_enforcement_initiative import (
                    synchronize as synchronize_enforcement,
                )

                synchronize_enforcement(self, c, action, event)
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import synchronize as synchronize_battle

                synchronize_battle(self, c, action, event, viewer, key)
            if action["data"].get("engage"):
                from girlframe.services.m3_engage import synchronize as synchronize_engage

                synchronize_engage(self, c, action, event, viewer, key)
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import synchronize as synchronize_doctor

                synchronize_doctor(self, c, action, event)
            if action["data"].get("void_keep"):
                from girlframe.services.m3_void_keep import synchronize_keep

                synchronize_keep(self, c, action, event, viewer, key)
            current_action = self.action(c, action["id"])
            if current_action["state"] == "complete" and current_action["data"].get(
                "gorgon_counter_source"
            ):
                from girlframe.services.m3_gorgon_play import complete_response

                complete_response(self, c, current_action, event, viewer, key)
            if (
                current_action["state"] == "complete"
                and current_action.get("parent_id")
                and current_action["data"].get("actor_basic")
            ):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(self).synchronize(c, current_action, event, viewer, key)
            elif current_action["state"] == "complete" and current_action["data"].get(
                "battle_counter_source"
            ):
                from girlframe.services.m3_battle import complete_counter_play

                complete_counter_play(self, c, current_action, event, viewer, key)
            current_action = self.action(c, action["id"])
            if current_action["state"] == "complete" and current_action["data"].get(
                "dormant_dive_source"
            ):
                from girlframe.services.m3_battle_dormant import complete_dive

                complete_dive(self, c, current_action, event, viewer, key)
            if current_action["state"] == "complete" and current_action["data"].get(
                "bomb_collar_source"
            ):
                from girlframe.services.m3_bomb_collar import complete_action as complete_collar

                complete_collar(self, c, current_action, event, key)
            c.execute(
                t.m2["m2_responses"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    choice_id=choice_id,
                    actor_id=str(viewer.user_id),
                    answer_json=answer.model_dump_json(),
                    event_id=event,
                )
            )
            if action["data"].get("am_code"):
                from girlframe.services.m3_am_body_consequences import synchronize as sync_am_body

                sync_am_body(self, c, event)
                action = self.action(c, action["id"])
            if action["data"].get("easy_target"):
                from girlframe.services.m3_easy_target import synchronize_npc_hurt

                synchronize_npc_hurt(self, c, self.action(c, action["id"]), event)
                action = self.action(c, action["id"])
            if action["data"].get("alpha_sex_counter_source"):
                from girlframe.services.m3_alpha_sex import synchronize_counters as sex_counters

                # Canonical component responses must exist before proving a completed Dose.
                sex_counters(self, c, event)
                action = self.action(c, action["id"])
            if action["data"].get("mockingbird"):
                from girlframe.services.m3_mockingbird_plays import (
                    post_synchronize as post_mockingbird,
                )

                post_mockingbird(self, c, action, event, viewer, key)
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import synchronize as synchronize_am

                synchronize_am(self, c, action, event)
            if action["data"].get("ankou_feedback") or action["data"].get("ankou_feedback_child"):
                from girlframe.services.m3_ankou_feedback import synchronize as synchronize_ankou

                synchronize_ankou(self, c, self.action(c, action["id"]), event)
            if action["data"].get("m3_finished"):
                from girlframe.services.m3_disposable_psyche import sync_off_duty

                sync_off_duty(self, c, action, event)
            if action["data"].get("princess_sex") or action["data"].get("princess_child"):
                from girlframe.services.m3_princess_sex import synchronize as sync_princess

                sync_princess(self, c, self.action(c, action["id"]), event)
            if action["data"].get("npc_flirt"):
                from girlframe.services.m3_npc_flirt import synchronize as sync_npc_flirt

                sync_npc_flirt(self, c, self.action(c, action["id"]), event)
            from girlframe.services.m3_bonded import synchronize_delegation

            synchronize_delegation(self, c, self.action(c, action["id"]), event)
            from girlframe.services.m3_changeling_hooks import (
                performance as observe_changeling_assault,
            )

            observe_changeling_assault(self, c, self.action(c, action["id"]), event)
            if action["data"].get("ankou"):
                from girlframe.services.m3_ankou import synchronize as sync_ankou

                sync_ankou(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["data"].get("changeling"):
                from girlframe.services.m3_changeling import synchronize as sync_changeling

                sync_changeling(self, c, self.action(c, action["id"]), event)
            if action["state"] == "complete" and action["data"].get("changeling_child"):
                from girlframe.services.m3_changeling_effects import (
                    complete_child as complete_changeling_child,
                )

                complete_changeling_child(self, c, state, self.action(c, action["id"]), event)
            if action["data"].get("red_queen"):
                from girlframe.services.m3_red_queen import synchronize as sync_red_queen

                sync_red_queen(self, c, self.action(c, action["id"]), event)
            if action["state"] == "complete" and action["data"].get("ankou_effect_child"):
                from girlframe.services.m3_ankou_feedback_sequences import (
                    complete_child as complete_ankou_effect_child,
                )

                complete_ankou_effect_child(self, c, state, self.action(c, action["id"]), event)
            if action["state"] == "complete" and action["data"].get("red_queen_child"):
                from girlframe.services.m3_red_queen_support import (
                    complete_child as complete_royal_child,
                )

                complete_royal_child(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["data"].get("wyvern"):
                from girlframe.services.m3_wyvern import synchronize as sync_wyvern

                sync_wyvern(self, c, self.action(c, action["id"]), event)
            if action["state"] == "complete" and action["data"].get("wyvern_pin_response"):
                from girlframe.services.m3_wyvern_combat import complete_pin_response

                complete_pin_response(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["state"] == "complete" and action["data"].get("wyvern_replacement"):
                from girlframe.services.m3_wyvern_combat import complete_replacement

                complete_replacement(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["data"].get("wyvern_child") and action["state"] == "complete":
                from girlframe.services.m3_wyvern import complete_child as complete_wyvern_child

                complete_wyvern_child(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["data"].get("bonded") or action["data"].get("bonded_child"):
                from girlframe.services.m3_bonded import synchronize as sync_bonded

                sync_bonded(self, c, self.action(c, action["id"]), event)
            if action["data"].get("consume_child") and action["state"] == "complete":
                from girlframe.services.m3_consume import complete_child as complete_consume_child

                complete_consume_child(
                    self,
                    c,
                    load_state(c, self.store.campaign_id),
                    self.action(c, action["id"]),
                    event,
                )
            if action["data"].get("prince"):
                from girlframe.services.m3_prince import synchronize as sync_prince

                sync_prince(self, c, self.action(c, action["id"]), event)
            if action["data"].get("consume") or row["kind"].startswith("consume_"):
                from girlframe.services.m3_consume import synchronize as sync_consume

                sync_consume(self, c, self.action(c, action["id"]), event)
            if action["data"].get("casualty_sex"):
                from girlframe.services.m3_casualty import synchronize as sync_casualty

                sync_casualty(self, c, self.action(c, action["id"]), event)
            if action["data"].get("investment_performance"):
                from girlframe.services.m3_vatgrown_plays import synchronize_investment_performance

                synchronize_investment_performance(self, c, self.action(c, action["id"]), event)
            if action["data"].get("vatgrown_sex"):
                from girlframe.services.m3_vatgrown_plays import synchronize as sync_vatgrown_sex

                sync_vatgrown_sex(self, c, self.action(c, action["id"]), event)
            if action["data"].get("newgirl_sex"):
                from girlframe.services.m3_newgirl_sex import synchronize as sync_newgirl

                sync_newgirl(self, c, self.action(c, action["id"]), event)
            if (
                action["data"].get("dose_up")
                or action["data"].get("vatgrown")
                or action["data"].get("easy_target")
            ):
                from girlframe.services.m3_role_punishments import (
                    synchronize as synchronize_source_role,
                )

                synchronize_source_role(self, c, action, event)
            if action["data"].get("alpha_sex"):
                from girlframe.services.m3_alpha_sex import synchronize as synchronize_alpha_sex

                synchronize_alpha_sex(self, c, action, event)
            from girlframe.services.m3_required_plays import synchronize as sync_required_play

            sync_required_play(self, c, self.action(c, action["id"]), event)
            if action["data"].get("alpha"):
                from girlframe.services.m3_alpha import synchronize as synchronize_alpha

                synchronize_alpha(self, c, action, event)
            if action["data"].get("janus"):
                from girlframe.services.m3_janus_play import synchronize as synchronize_janus

                synchronize_janus(self, c, action, event)
            if action["data"].get("snoop"):
                from girlframe.services.m3_enforcer_snoop import synchronize as synchronize_snoop

                synchronize_snoop(self, c, action, event)
            from girlframe.services.m3_virus_orders import post_response as post_virus_order

            post_virus_order(self, c, self.action(c, action["id"]), event)
            from girlframe.services.m3_casualty_support import (
                post_response as casualty_post_response,
            )

            casualty_post_response(self, c, event, viewer, key)
            if action["data"].get("easy_target_child"):
                from girlframe.services.m3_easy_target import synchronize as sync_easy_child

                sync_easy_child(self, c, self.action(c, action["id"]), event)
            if action["data"].get("changeling_remote"):
                from girlframe.services.m3_changeling_sex import (
                    synchronize_action as sync_remote_source,
                )

                sync_remote_source(self, c, self.action(c, action["id"]), event)
            return {"action_id": action["id"], "state": action["state"], "choice_id": choice_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.choice_resolved",
                {
                    "choice_id": choice_id,
                    "revision": revision,
                    "answer": answer.model_dump(mode="json"),
                },
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def issue_order(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        target: int,
        text: str,
        *,
        dose_up: bool = False,
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("Provide a direct order in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.scene(c, channel)
            self.pilot_cast(c, state, scene, owners=(viewer.user_id, target))
            if (
                viewer.user_id not in scene["participants"]
                or target not in scene["participants"]
                or str(target) not in state.sheets
            ):
                raise WorkflowError(
                    "Only a current superior in this scene can issue a direct order."
                )
            from girlframe.services.m3_bonded_support import issue_requested_order

            requested = issue_requested_order(
                self, c, state, viewer, key, channel, target, text, dose_up=dose_up
            )
            if requested is not None:
                return requested
            authority = None
            am_secret = None
            from girlframe.services.m3_gender_designation import (
                order_authority as gender_order_authority,
            )

            gender_authority = (
                gender_order_authority(self, c, state, viewer.user_id, target)
                if str(viewer.user_id) in state.sheets
                else None
            )
            from girlframe.services.m3_stim_sex import order_authority as stim_order_authority

            stim_authority = stim_order_authority(self, c, state, viewer.user_id, target)
            if (
                not higher(state, viewer.user_id, target)
                and gender_authority is None
                and stim_authority is None
            ):
                from girlframe.services.m3_am_scrutinized import pilot_order_authority

                am_secret = pilot_order_authority(self, c, state, viewer.user_id, target)
                if am_secret is None:
                    from girlframe.services.m3_succubus import issue_authority

                    authority = issue_authority(self, c, state, viewer.user_id, target)
                    if authority is None:
                        raise WorkflowError(
                            "A current superior or qualifying order source is required."
                        )
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the current action first.")
            identity, order_id = str(uuid4()), str(uuid4())
            dose_order = None
            order_event = None
            if dose_up:
                from girlframe.services.m3_dose_up import _access as dose_access
                from girlframe.services.m3_dose_up import stage_order

                dose_access(self, c, viewer)
                order_event = str(uuid4())
                dose_order = stage_order(
                    self, c, state, viewer.user_id, target, order_id, channel, order_event
                )
            c.execute(
                t.m2["m2_orders"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=order_id,
                    issuer_id=str(viewer.user_id),
                    target_id=str(target),
                    channel_id=str(channel),
                    body_json=json.dumps(
                        {"text": text}
                        | ({"am_secret": am_secret} if am_secret else {})
                        | ({"succubus": authority} if authority else {})
                        | ({"gender_designation": gender_authority} if gender_authority else {})
                        | ({"dose_up": dose_order} if dose_order else {})
                        | ({"stim_sex": stim_authority} if stim_authority else {})
                    ),
                    state="awaiting_response",
                )
            )
            data = {
                "play": "receive_orders",
                "character_ids": {
                    str(uid): self.character_binding(c, state, uid, require_current_profile=False)
                    for uid in scene["participants"]
                    if str(uid) in state.sheets
                },
                "order_id": order_id,
                "order_text": text,
                "participants": scene["participants"],
                "handler": state.handler,
                "depth": 0,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            from girlframe.services.m3_recovery import enable as enable_recovery

            enable_recovery(self, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(target),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            table = t.m2["m2_locks"]
            values = {
                "action_id": identity,
                "state": "acquiring",
                "body_json": "{}",
                "lease_until": 0,
                "claim_token": None,
            }
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            order_source_payload: dict[str, Any] = (
                {"stim_sex": stim_authority} if stim_authority else {}
            )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.order_issued",
                state if dose_order or stim_authority else None,
                event_id=order_event,
                action_id=identity,
                **order_source_payload,
            )
            return {"action_id": identity, "order_id": order_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.order_issued",
                {"channel": channel, "target": target, "text": text}
                | ({"dose_up": True} if dose_up else {}),
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def abort(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            action = self.action(c, identity)
        if action["data"].get("virus_purge"):
            from girlframe.services.m3_virus_operations import OperationService

            return OperationService(self).cancel(viewer, key, identity)

        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            if (
                not (viewer.is_administrator and self.store.policy.allow_guild_administrators)
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError(
                    "Only configured staff or the appointed Handler can recover an action."
                )

        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            if action["parent_id"]:
                raise WorkflowError("Recover the root action so its scene lock is restored safely.")
            lock = self.lock(c, action["channel_id"])
            if not lock or lock["action_id"] != identity or lock["state"] == "released":
                raise WorkflowError("STALE_ACTION: this action no longer owns the channel lock.")
            if action["state"] == "complete":
                raise WorkflowError(
                    "Completed effects remain canonical; use emergency restoration."
                )
            table = t.m2["m2_actions"]
            # Root abort also stops descendant decisions; existing receipts/spends remain immutable.
            rows = [
                dict(x)
                for x in c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == action["channel_id"],
                        table.c.state.not_in(("complete", "aborted")),
                    )
                ).mappings()
            ]
            from girlframe.services.m3_recovery import capture

            interruption_event = str(uuid4())
            interruptions = capture(self, c, action, rows, interruption_event)
            for row in rows:
                child = self.action(c, row["id"])
                choices = t.m2["m2_choices"]
                if child["id"] in interruptions:
                    child["data"]["shared_recovery"] = interruptions[child["id"]].model_dump(
                        mode="json"
                    )
                if action["data"].get("m3") or action["data"].get("actor_basic"):
                    recovery_key = (
                        "actor_recovery" if action["data"].get("actor_basic") else "m3_recovery"
                    )
                    child["data"][recovery_key] = {
                        "root": identity,
                        "state": child["state"],
                        "choices": [
                            {k: item[k] for k in ("id", "state", "revision")}
                            for item in c.execute(
                                sa.select(choices).where(
                                    choices.c.campaign_id == self.store.campaign_id,
                                    choices.c.action_id == child["id"],
                                    choices.c.state.in_(("pending", "submitted")),
                                )
                            ).mappings()
                        ],
                    }
                self.save_action(c, child, state="aborted")
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.action_id == child["id"],
                        choices.c.state.in_(("pending", "submitted")),
                    )
                    .values(state="aborted")
                )
            if action["state"] == "complete":
                raise WorkflowError(
                    "Completed effects remain canonical; use emergency restoration."
                )
            self.queue(c, action, "aborted")
            locks = t.m2["m2_locks"]
            c.execute(
                locks.update()
                .where(locks.c.campaign_id == self.store.campaign_id, locks.c.action_id == identity)
                .values(state="releasing", lease_until=0, claim_token=None)
            )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.action_aborted",
                action_id=identity,
                event_id=interruption_event,
            )
            return {
                "action_id": identity,
                "state": "aborted",
                "receipt_preserved": bool(action["data"]["receipt"]),
            }

        return self.store._write(
            viewer,
            key,
            "m2.action_aborted",
            {"action_id": identity},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            action = self.action(c, identity)
            if action["data"].get("virus_order"):
                from girlframe.services.m3_virus_orders import VirusOrderService

                return VirusOrderService(self).inspect(viewer, identity)
            if action["data"].get("virus_purge"):
                from girlframe.services.m3_virus_operations import OperationService

                return OperationService(self).inspect(viewer, identity)
            if action["data"].get("harpy_defeat"):
                from girlframe.services.m3_harpy_defeat import HarpyDefeatService

                return HarpyDefeatService(self.store, self).inspect(viewer, identity)
            if action["data"].get("leviathan_obsession"):
                from girlframe.services.m3_leviathan_obsession import ObsessionService

                return ObsessionService(self).inspect(viewer, identity)
            snoop = action["data"].get("snoop")
            allowed = set(action["data"]["participants"])
            if snoop:
                allowed.update((snoop["target_controller"], snoop["procedural_gm"]))
            if viewer.user_id not in allowed:
                raise WorkflowError("This action is not visible to you.")
            if action["data"].get("learned_hound_status"):
                from girlframe.services.m3_learned_plays import prove_hound_status

                prove_hound_status(self, c, load_state(c, self.store.campaign_id), action)
            result = action["data"]["result"] if action["state"] == "complete" else None
            parties = {int(action["actor_id"]), action["data"].get("prepared", {}).get("target")}
            if result and action["data"].get("janus"):
                from girlframe.services.m3_janus_play import visible_result as visible_janus

                result = visible_janus(
                    result, action["data"]["janus"], viewer, load_state(c, self.store.campaign_id)
                )
            elif result and snoop:
                from girlframe.services.m3_enforcer_snoop import visible_result

                result = visible_result(action, viewer, result)
            elif result and viewer.user_id not in parties:
                result = {k: v for k, v in result.items() if k in ("total", "tier")}
            return {
                "id": identity,
                "state": action["state"],
                "revision": action["revision"],
                "play": action["data"]["play"],
                "receipt": action["data"]["receipt"],
                "modifiers": [
                    {k: v for k, v in x.items() if k in ("source", "amount")}
                    for x in action["data"]["modifiers"]
                ],
                "result": result,
            }

    def rebuild(self) -> int:
        with self.store.transaction() as c:
            table = t.m2["m2_state_history"]
            row = (
                c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return 0
            state = GameState.model_validate_json(row["body_json"])
            view = t.m2["m2_state"]
            c.execute(view.delete().where(view.c.campaign_id == self.store.campaign_id))
            c.execute(
                view.insert().values(
                    campaign_id=self.store.campaign_id,
                    revision=state.revision,
                    body_json=state.model_dump_json(),
                )
            )
            self.store._audit(
                c,
                "system:local_operator",
                str(uuid4()),
                "m2.projection_rebuilt",
                {"game_revision": state.revision},
                ruleset_version=RULESET,
            )
            return state.revision

    def fulfill(
        self, viewer: GuildViewer, key: str, channel: int, obligation_id: str, text: str
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("Describe the source-backed follow-through action.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.scene(c, channel)
            self.pilot_cast(c, state, scene, owners=(viewer.user_id,))
            obligation = next(
                (
                    x
                    for x in state.obligations
                    if x.id == obligation_id and x.owner == viewer.user_id and x.state == "pending"
                ),
                None,
            )
            if obligation is None or obligation.kind not in ("flirt_followthrough", "reject_tag"):
                raise WorkflowError(
                    "This obligation has no implemented owner follow-through action."
                )
            if obligation.kind == "flirt_followthrough" and obligation.target is not None:
                self.pilot_cast(c, state, scene, owners=(obligation.target,))
            if (
                viewer.user_id not in scene["participants"]
                or state.handler not in scene["participants"]
                or (
                    obligation.kind == "flirt_followthrough"
                    and obligation.target not in scene["participants"]
                )
            ):
                raise WorkflowError("The required actors must join this scene.")
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the current action first.")
            identity = str(uuid4())
            data = {
                "play": obligation.kind,
                "character_ids": {
                    str(uid): self.character_binding(c, state, uid, require_current_profile=False)
                    for uid in scene["participants"]
                    if str(uid) in state.sheets
                },
                "obligation_id": obligation_id,
                "context": text,
                "participants": scene["participants"],
                "handler": state.handler,
                "depth": 0,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            from girlframe.services.m3_recovery import enable as enable_recovery

            enable_recovery(self, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            table = t.m2["m2_locks"]
            values = {
                "action_id": identity,
                "state": "acquiring",
                "body_json": "{}",
                "lease_until": 0,
                "claim_token": None,
            }
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.event(c, viewer.user_id, key, "m2.followthrough_confirmed", action_id=identity)
            return {"action_id": identity}

        return self.store._write(
            viewer,
            key,
            "m2.followthrough_confirmed",
            {"channel": channel, "obligation": obligation_id, "text": text},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def own_obligations(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return [
                x.model_dump(mode="json")
                for x in state.obligations
                if x.owner == viewer.user_id and x.state == "pending"
            ]

    def retry_recovery(
        self, viewer: GuildViewer, key: str, identity: str, *, restore_only: bool = False
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            if (
                not (viewer.is_administrator and self.store.policy.allow_guild_administrators)
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError("Only configured staff can reconcile deliveries or unlock.")

        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            if action["parent_id"]:
                raise WorkflowError("Recover the root scene action.")
            locks = t.m2["m2_locks"]
            current = self.lock(c, action["channel_id"])
            if not current or current["action_id"] != identity or current["state"] == "released":
                raise WorkflowError("STALE_ACTION: this action no longer owns the channel lock.")
            if restore_only:
                if action["state"] not in ("complete", "aborted"):
                    raise WorkflowError(
                        "Abort the pending root action before emergency restoration."
                    )
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id, locks.c.action_id == identity
                    )
                    .values(state="releasing", lease_until=0, claim_token=None)
                )
            else:
                jobs = t.m2["m2_outbox"]
                c.execute(
                    jobs.update()
                    .where(
                        jobs.c.campaign_id == self.store.campaign_id,
                        jobs.c.action_id == identity,
                        jobs.c.state == "review",
                    )
                    .values(state="pending", lease_until=0, claim_token=None)
                )
                row = self.lock(c, action["channel_id"])
                if row and row["state"] == "review":
                    c.execute(
                        locks.update()
                        .where(
                            locks.c.campaign_id == self.store.campaign_id,
                            locks.c.action_id == identity,
                        )
                        .values(
                            state="releasing"
                            if action["state"] in ("complete", "aborted")
                            else "acquiring",
                            lease_until=0,
                            claim_token=None,
                        )
                    )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.staff_reconciliation",
                action_id=identity,
                restore_only=restore_only,
            )
            return {"action_id": identity, "restore_only": restore_only}

        return self.store._write(
            viewer,
            key,
            "m2.staff_reconciliation",
            {"action_id": identity, "restore_only": restore_only},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def close_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            self.gate()
            self.store.administrator(viewer)

        def operation(c: Connection) -> dict[str, Any]:
            scene = self.scene(c, channel)
            from girlframe.services.p1_source_pause import require_clear as require_source_clear

            require_source_clear(self, c, channel)
            from girlframe.engine.m3_deep_brain_spikes import require_return

            try:
                require_return(load_state(c, self.store.campaign_id), scene["id"])
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError(
                    "Resolve or recover the pending action before closing this scene."
                )
            actions = t.m2["m2_actions"]
            for body in c.scalars(
                sa.select(actions.c.body_json).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.scene_id == scene["id"],
                    actions.c.state == "aborted",
                )
            ):
                saved = json.loads(body)
                if saved.get("shared_recovery"):
                    raise WorkflowError("Resume or cancel the saved Play before closing its scene.")
                if saved.get("receipt") and (
                    saved.get("m3_recovery") or saved.get("actor_recovery")
                ):
                    raise WorkflowError(
                        "Resume the actual known roll before closing its original scene."
                    )
            work = t.m3["m3_required_work"]
            latest = {
                x["id"]: x
                for x in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }
            if any(
                x["scene_id"] == scene["id"] and x["state"] != "resolved" for x in latest.values()
            ):
                raise WorkflowError("Resolve the actual source-bound scene work before closing it.")
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(open=False)
            )
            state = load_state(c, self.store.campaign_id)
            cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
            if cast:
                state.scene_casts = [
                    x.model_copy(update={"open": False, "revision": x.revision + 1})
                    if x.id == cast.id
                    else x
                    for x in state.scene_casts
                ]
            close_event = str(uuid4())
            from girlframe.services.m3_ankou import expire_scene as expire_ankou_scene

            drugs_changed = expire_ankou_scene(self, c, state, scene["id"], close_event)
            if any(x.get("kind") == "stim_sex_drug" for x in state.facts):
                from girlframe.services.m3_stim_sex import expire_scene as expire_stim

                drugs_changed = expire_stim(self, c, state, scene, close_event) or drugs_changed
            if any(x.get("kind") == "dose_up_result" for x in state.facts):
                from girlframe.services.m3_dose_up import expire_scene

                drugs_changed = expire_scene(self, c, state, scene, close_event) or drugs_changed
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.scene_closed",
                state if cast or drugs_changed else None,
                channel=channel,
                event_id=close_event,
            )
            return {"channel": channel, "closed": True}

        return self.store._write(
            viewer,
            key,
            "m2.scene_closed",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def scene_info(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            scene = self.scene(c, channel)
            lock = self.lock(c, channel)
            if viewer.user_id not in scene["participants"]:
                return {"participants": [], "lock": None, "joined": False}
            state = load_state(c, self.store.campaign_id)
            cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
            native = {x.controller for x in cast.roles if x.actor.kind == "pilot"} if cast else None
            from girlframe.engine.m3_actor_bonds import current_ref
            from girlframe.engine.m3_deep_brain_spikes import scene_context
            from girlframe.engine.m3_prince import presentation

            perceived = {
                str(uid): part
                for uid in scene["participants"]
                if str(uid) in state.sheets
                and (part := presentation(state, current_ref(state, uid), scene["id"])) is not None
            }
            return {
                "perceived_parts": perceived,
                "pilots": [
                    uid
                    for uid in scene["participants"]
                    if str(uid) in state.sheets and (native is None or uid in native)
                ],
                "labels": {
                    str(uid): state.sheets[str(uid)].callsign
                    if str(uid) in state.sheets
                    else "Handler"
                    for uid in scene["participants"]
                },
                "memory": scene_context(state, scene["id"]),
                "participants": scene["participants"],
                "lock": {k: lock[k] for k in ("action_id", "state")} if lock else None,
                "joined": True,
            }

    def decision(self, viewer: GuildViewer, choice_id: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            table = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == choice_id,
                        table.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision is no longer available to you.")
            from girlframe.services.m3_princess_sex import decision_author

            original_action = self.action(c, row["action_id"])
            scoped_author = decision_author(
                self, c, load_state(c, self.store.campaign_id), original_action, dict(row)
            )
            if viewer.user_id != (
                scoped_author if scoped_author is not None else int(row["actor_id"])
            ):
                raise WorkflowError("This decision is no longer available to you.")
            if row["kind"] == "battle_sprite_intercept":
                from girlframe.services.m3_sprite import SpriteService

                return SpriteService(self.store).decision(viewer, choice_id)
            action = self.action(c, row["action_id"])
            if row["kind"].startswith("npc_flirt_") and action["data"].get("npc_flirt"):
                from girlframe.services.m3_npc_flirt import authorize as npc_flirt_authorize
                from girlframe.services.m3_npc_flirt import projection as npc_flirt_projection

                npc_flirt_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    npc_flirt=npc_flirt_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"] in ("oldgen_write_maxim", "oldgen_low_maxim", "oldgen_listen"):
                from girlframe.services.m3_oldgen import detail as oldgen_detail

                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=oldgen_detail(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("vat_doll_"):
                from girlframe.services.m3_vatgrown import authorize as doll_authorize
                from girlframe.services.m3_vatgrown import projection as doll_projection

                doll_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=doll_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("oldgen_sex_"):
                from girlframe.services.m3_oldgen_sex import authorize as oldgen_sex_authorize
                from girlframe.services.m3_oldgen_sex import projection as oldgen_sex_projection

                oldgen_sex_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=oldgen_sex_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("prince_"):
                from girlframe.services.m3_prince import projection as prince_projection

                detail = prince_projection(
                    self, c, load_state(c, self.store.campaign_id), action, dict(row)
                )
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    prince=detail,
                    detail=detail,
                )
            if row["kind"].startswith("ankou_") and not row["kind"].startswith("ankou_feedback"):
                from girlframe.services.m3_ankou import (
                    authorize as ankou_authorize,
                )
                from girlframe.services.m3_ankou import (
                    projection as ankou_projection,
                )

                ankou_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    detail=ankou_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"] == "changeling_interrupt":
                from girlframe.services.m3_changeling_hooks import interruption

                detail = interruption(
                    self, c, viewer, load_state(c, self.store.campaign_id), action, dict(row)
                )
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=detail,
                )
            if row["kind"].startswith("changeling_"):
                from girlframe.services.m3_changeling import authorize as changeling_authorize
                from girlframe.services.m3_changeling import projection as changeling_projection

                changeling_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    detail=changeling_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("red_queen_"):
                from girlframe.services.m3_red_queen import authorize as royal_authorize
                from girlframe.services.m3_red_queen import projection as royal_projection

                royal_authorize(self, c, viewer, action)
                detail = royal_projection(
                    self, c, load_state(c, self.store.campaign_id), action, dict(row)
                )
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    detail=detail,
                )
            if row["kind"].startswith("wyvern_"):
                from girlframe.services.m3_wyvern import authorize as wyvern_authorize
                from girlframe.services.m3_wyvern import projection as wyvern_projection

                wyvern_authorize(self, c, viewer, action)
                detail = (
                    dict(handler_grant=json.loads(row["body_json"]).get("handler_grant"))
                    if row["kind"] == "wyvern_handler"
                    else wyvern_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    )
                )
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    detail=detail,
                )
            if row["kind"].startswith("bonded_"):
                from girlframe.services.m3_bonded import authorize as bonded_authorize
                from girlframe.services.m3_bonded import projection as bonded_projection

                bonded_authorize(self, c, viewer, action)
                detail = bonded_projection(self, c, viewer, action, dict(row))
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    detail=detail,
                    bonded=detail,
                )
            if row["kind"].startswith("consume_"):
                from girlframe.services.m3_consume import projection as consume_projection

                detail = consume_projection(
                    self, c, load_state(c, self.store.campaign_id), action, dict(row)
                )
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    consume=detail,
                    detail=detail,
                )
            if row["kind"].startswith("casualty_"):
                from girlframe.services.m3_casualty import authorize as casualty_sex_authorize
                from girlframe.services.m3_casualty import projection as casualty_sex_projection

                if row["kind"] == "casualty_roll_push":
                    from girlframe.services.m3_access import Access

                    gate = Access(self.store)
                    gate.authorize(c, viewer, "plays")
                    assert gate.registry is not None
                    gate.registry.require_available("girl.casualty.wounded-god")
                else:
                    casualty_sex_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=casualty_sex_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("vat_sex_"):
                from girlframe.services.m3_vatgrown_plays import authorize as vatgrown_sex_authorize
                from girlframe.services.m3_vatgrown_plays import (
                    projection as vatgrown_sex_projection,
                )

                vatgrown_sex_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=vatgrown_sex_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("newgirl_sex_"):
                from girlframe.services.m3_newgirl_sex import authorize as newgirl_sex_authorize
                from girlframe.services.m3_newgirl_sex import projection as newgirl_sex_projection

                newgirl_sex_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=newgirl_sex_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if (
                row["kind"] == "battle_target_damage"
                and action["data"].get("easy_target")
                and json.loads(row["body_json"]).get("easy_target_npc_hurt")
            ):
                from girlframe.services.m3_easy_target import authorize as easy_target_authorize
                from girlframe.services.m3_easy_target import npc_hurt_damage_projection

                easy_target_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    battle=npc_hurt_damage_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("easy_target_"):
                from girlframe.services.m3_easy_target import authorize as easy_target_authorize
                from girlframe.services.m3_easy_target import projection as easy_target_projection

                easy_target_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=easy_target_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("stim_sex_"):
                from girlframe.services.m3_stim_sex import authorize as stim_authorize
                from girlframe.services.m3_stim_sex import projection as stim_projection

                stim_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    detail=stim_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("ankou_feedback_"):
                from girlframe.services.m3_ankou_feedback import projection as ankou_projection

                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    ankou_feedback=ankou_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"].startswith("princess_sex_"):
                from girlframe.services.m3_princess_sex import authorize as princess_authorize
                from girlframe.services.m3_princess_sex import projection as princess_projection

                princess_authorize(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    princess_sex=princess_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"] in ("dose_up_components", "dose_up_target_low"):
                from girlframe.services.m3_dose_up import choice_projection as dose_projection

                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    detail=dose_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if row["kind"] in (
                "gender_partner_tag_resolution",
                "gender_animal_tag",
                "gender_partner_paired",
            ):
                from girlframe.services.m3_gender_designation import choice_projection

                projected = choice_projection(
                    self, c, load_state(c, self.store.campaign_id), action, dict(row)
                )
                if projected is None:
                    raise WorkflowError("Recover the original designation response source")
                current_state = load_state(c, self.store.campaign_id)
                own = current_state.sheets.get(str(viewer.user_id))
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    play=action["data"]["play"],
                    result={
                        key: value
                        for key, value in action["data"]["result"].items()
                        if key in ("tier", "total")
                    },
                    own=own.model_dump(mode="json") if own is not None else None,
                    gender=projected,
                )
            if row["kind"] == "reign_group_tag_resolution":
                from girlframe.services.m3_reign_terror import project_resolution

                return dict(row) | dict(
                    reign=project_resolution(
                        self, c, load_state(c, self.store.campaign_id), dict(row)
                    ),
                    body=json.loads(row["body_json"]),
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    result={},
                )
            if row["kind"] == "sidearm_reconsider":
                from girlframe.services.m3_hidden_sidearm import projection as sidearm_projection

                return dict(row) | dict(
                    sidearm=sidearm_projection(
                        self, c, load_state(c, self.store.campaign_id), action
                    ),
                    body=json.loads(row["body_json"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result={},
                )
            if row["kind"] in (
                "secretary_gunpoint",
                "secretary_response_play",
                "secretary_gunpoint_resolution",
            ):
                from girlframe.services.m3_secretary import response_projection

                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    secretary=response_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    actor=int(action["actor_id"]),
                    play=action["data"]["play"],
                    result={},
                )
            if action["data"].get("leviathan_obsession"):
                from girlframe.services.m3_leviathan_obsession import ObsessionService

                return ObsessionService(self).decision(c, viewer, action, dict(row))
            if action["data"].get("virus_order"):
                from girlframe.services.m3_virus_orders import VirusOrderService

                return VirusOrderService(self).decision(c, viewer, action, dict(row))
            if action["data"].get("virus_purge"):
                from girlframe.services.m3_virus_operations import OperationService

                return OperationService(self).decision(c, viewer, action, dict(row))
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                return GorgonPlayService(self).decision(c, viewer, action, dict(row))
            if action["data"].get("am_code_source") and row["kind"] == "am_code_prepare":
                from girlframe.services.m3_am_code import access as code_access

                code_access(self, c, viewer)
                if int(action["actor_id"]) != viewer.user_id:
                    raise WorkflowError("Only the original AM prepares her actual maintenance")
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play="am_code_maintenance",
                    result={},
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    am_code=dict(prepare=True),
                )
            if action["data"].get("am_code") and row["kind"].startswith("am_code_"):
                from girlframe.services.m3_am_code import authorize as authorize_code
                from girlframe.services.m3_am_code import projection as project_code

                authorize_code(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play="am_just_code",
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    am_code=project_code(self, c, state, action, dict(row)),
                )
            if action["data"].get("am_source") and row["kind"] == "am_prepare":
                from girlframe.services.m3_am_scrutinized import preparation as prepare_source_am

                state = load_state(c, self.store.campaign_id)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play="am_discovery",
                    result={},
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    am_scrutinized=prepare_source_am(self, c, state, action, viewer),
                )
            if action["data"].get("am_scrutinized") and row["kind"] == "battle_defeat":
                from girlframe.services.m3_am_scrutinized import pilot_defeat_projection

                return dict(row) | pilot_defeat_projection(
                    self, c, load_state(c, self.store.campaign_id), action, dict(row)
                )
            if action["data"].get("am_scrutinized") and row["kind"].startswith("am_"):
                from girlframe.services.m3_am_scrutinized import authorize as authorize_am
                from girlframe.services.m3_am_scrutinized import projection as project_am

                authorize_am(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play="am_scrutinized",
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    am_scrutinized=project_am(self, c, state, action, dict(row)),
                )
            if action["data"].get("alpha_sex") and (
                row["kind"].startswith("alpha_sex_") or row["kind"].startswith("battle_")
            ):
                from girlframe.services.m3_alpha_sex import authorize as authorize_alpha_sex
                from girlframe.services.m3_alpha_sex import projection as alpha_sex_projection

                authorize_alpha_sex(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                extra = {}
                if row["kind"].startswith("battle_"):
                    from girlframe.services.m3_battle import damage_projection

                    extra["battle"] = damage_projection(self, c, state, action, dict(row))
                return (
                    dict(row)
                    | dict(
                        body=json.loads(row["body_json"]),
                        play="alpha_sex",
                        result={
                            k: v
                            for k, v in action["data"]["result"].items()
                            if k in ("tier", "total")
                        },
                        actor=int(action["actor_id"]),
                        parent=action["id"],
                        channel=int(action["channel_id"]),
                        alpha_sex=alpha_sex_projection(self, c, state, action, dict(row)),
                    )
                    | extra
                )
            if action["data"].get("alpha") and (
                row["kind"].startswith("alpha_") or row["kind"].startswith("battle_")
            ):
                from girlframe.services.m3_alpha import authorize as authorize_alpha
                from girlframe.services.m3_alpha import projection as alpha_projection

                authorize_alpha(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                extra = {}
                if row["kind"].startswith("battle_"):
                    from girlframe.services.m3_battle import damage_projection

                    extra["battle"] = damage_projection(self, c, state, action, dict(row))
                return (
                    dict(row)
                    | dict(
                        body=json.loads(row["body_json"]),
                        play=action["data"]["play"],
                        result={
                            k: v
                            for k, v in action["data"]["result"].items()
                            if k in ("tier", "total")
                        },
                        actor=int(action["actor_id"]),
                        parent=action["id"],
                        channel=int(action["channel_id"]),
                        alpha=alpha_projection(self, c, state, action, dict(row)),
                    )
                    | extra
                )
            if action["data"].get("doctor") and row["kind"].startswith("doctor_"):
                from girlframe.services.m3_doctor import authorize as authorize_doctor
                from girlframe.services.m3_doctor import projection as doctor_projection

                authorize_doctor(self, c, viewer, action)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play=action["data"]["play"],
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    doctor=doctor_projection(
                        self, c, load_state(c, self.store.campaign_id), action, dict(row)
                    ),
                )
            if action["data"].get("janus") and row["kind"].startswith("janus_"):
                from girlframe.services.m3_janus_play import authorize as authorize_janus
                from girlframe.services.m3_janus_play import projection as janus_projection

                authorize_janus(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play=action["data"]["play"],
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    janus=janus_projection(self, c, viewer, state, action, dict(row)),
                )
            if action["data"].get("snoop") and row["kind"].startswith("snoop_"):
                from girlframe.services.m3_enforcer_snoop import authorize as authorize_snoop
                from girlframe.services.m3_enforcer_snoop import projection as snoop_projection

                authorize_snoop(self, c, viewer, action)
                state = load_state(c, self.store.campaign_id)
                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play=action["data"]["play"],
                    result={
                        k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")
                    },
                    actor=int(action["actor_id"]),
                    parent=action["id"],
                    channel=int(action["channel_id"]),
                    snoop=snoop_projection(self, c, viewer, state, action, dict(row)),
                )
            if action["data"].get("harpy_defeat"):
                from girlframe.services.m3_harpy_defeat import HarpyDefeatService

                return HarpyDefeatService(self.store, self).decision(viewer, choice_id)
            if action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                return ActorPlayService(self).decision(c, viewer, action, dict(row))
            if action["data"].get("npc_order"):
                from girlframe.services.m3_npc_orders import authorize as authorize_npc_order

                authorize_npc_order(self, c, viewer, action)
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_battle_dormant import proved_converted_originals

            converted_originals = proved_converted_originals(self, c, state, action)
            self.action_characters(c, action, state, allowed_archived=converted_originals)
            if converted_originals and action["data"].get("battle"):
                from girlframe.services.m3_battle import projection as battle_projection

                return dict(row) | dict(
                    body=json.loads(row["body_json"]),
                    play=action["data"]["play"],
                    result=action["data"]["result"],
                    actor=int(action["actor_id"]),
                    own=None,
                    tags=[],
                    battle=battle_projection(self, c, state, action, dict(row)),
                )
            actor = state.sheets[str(action["actor_id"])]
            learned_keep_rule = None
            if action["data"].get("learned_keep_rider"):
                from girlframe.services.m3_learned_plays import active_keep_rider_rule

                learned_keep_rule = active_keep_rider_rule(self, c, state, action)
            decision_owner = int(row["actor_id"]) if scoped_author is not None else viewer.user_id
            own = state.sheets.get(str(decision_owner))
            # Return only selectable entities needed by this decision, never another private sheet.
            body = json.loads(row["body_json"])
            from girlframe.services.m3_bomb_collar import tags as collar_tags
            from girlframe.services.m3_cute_uniforms import tags as uniform_tags

            tags = [
                x.model_dump(mode="json")
                for x in actor.tags
                + uniform_tags(state, actor.owner)
                + collar_tags(state, actor.owner)
                if decision_owner in x.observers or decision_owner == actor.owner
            ]
            if (
                action["data"].get("kicked_puppy")
                and row["kind"] == "tag_window"
                and viewer.user_id == actor.owner
            ):
                from girlframe.engine.m3_actor_state import ActorRef as ChampionActor
                from girlframe.engine.m3_girl_runtime_state import has_rule as kicked_has_rule
                from girlframe.engine.m3_girl_runtime_state import mentor_tag as kicked_mentor_tag
                from girlframe.services.m3_ankou import self_tag as champion_self_tag
                from girlframe.services.m3_dose_up import self_tag as drug_self_tag
                from girlframe.services.m3_kicked_puppy import self_tag as kicked_self_tag
                from girlframe.services.m3_stim_sex import self_tag as stim_self_tag

                tags = [
                    x.model_dump(mode="json")
                    for x in actor.tags
                    + uniform_tags(state, actor.owner)
                    + collar_tags(state, actor.owner)
                    if kicked_self_tag(self, c, state, action, viewer.user_id, x)
                    or drug_self_tag(self, c, state, action, viewer.user_id, x)
                    or stim_self_tag(self, c, state, action, viewer.user_id, x)
                    or actor.character_id is not None
                    and champion_self_tag(
                        self,
                        c,
                        state,
                        ChampionActor(
                            kind="pilot", entity=str(actor.owner), incarnation=actor.character_id
                        ),
                        x.id,
                    )
                    or kicked_mentor_tag(actor, x, state)
                    or kicked_has_rule(actor, "girl.princess.objectively-beautiful", "PRINCESS")
                    or (
                        learned_keep_rule == "girl.princess.objectively-beautiful"
                        and action["data"]["play"] == "flirt"
                    )
                ]
            if decision_owner == actor.owner and row["kind"] == "tag_window":
                from girlframe.services.m3_control_ritual import candidates as ritual_candidates

                tags += [
                    x.model_dump(mode="json") for x in ritual_candidates(state, action, actor.owner)
                ]
            own_data = own.model_dump(mode="json") if own else None
            if scoped_author is not None and own_data is not None:
                # Only the mechanical inputs needed for this exact actor-owned decision.
                fields = {
                    "owner",
                    "girl",
                    "identities",
                    "assets",
                    "harpy",
                    "retained_plays",
                    "sedation_locked",
                    "status_marked",
                }
                own_data = {k: v for k, v in own_data.items() if k in fields}
                runtime = own.girl_runtime if own else None
                own_data["girl_runtime"] = (
                    {
                        "swaps": [x.model_dump(mode="json") for x in runtime.swaps],
                        "retained_rules": list(runtime.retained_rules),
                    }
                    if runtime
                    else None
                )
            if scoped_author is not None and own_data is not None:
                if row["kind"] != "tag_resolution":
                    own_data["identities"] = []
                own_data["assets"] = []
            if own is not None and own_data is not None:
                from girlframe.engine.m3_clone_am import additional_identities
                from girlframe.services.m3_clone_am import prove_additional

                additional = additional_identities(state, own.owner)
                if additional:
                    prove_additional(self, c, state, own.owner)
                own_data["additional_identities"] = [x.model_dump(mode="json") for x in additional]
                if scoped_author is None:
                    from girlframe.engine.m3_oldgen import marked_maxims

                    own_data["marked_maxims"] = [
                        {"id": key, "name": name, "marked": True}
                        for key, name in marked_maxims(state, own.owner)
                    ]
                own_data.setdefault("tags", [])
                own_data["tags"] += [
                    x.model_dump(mode="json") for x in uniform_tags(state, own.owner)
                ]
            if scoped_author is not None:
                if row["kind"] != "tag_resolution" and own_data is not None:
                    own_data["additional_identities"] = []
                if row["kind"] not in ("tag_window", "tag_resolution"):
                    tags = []
            from girlframe.engine.m3_actors import resolve as resolve_reign_actor
            from girlframe.services.m3_actors import profiles as reign_profiles
            from girlframe.services.m3_reign_terror import candidates as reign_candidates

            reign_tags = (
                reign_candidates(self, c, state, action) if row["kind"] == "tag_window" else []
            )
            eligible_reign = []
            for item in reign_tags:
                from girlframe.services.m3_reign_terror import member as reign_member

                subject = reign_member(self, c, state, item.id).target
                if (
                    resolve_reign_actor(
                        state, subject, reign_profiles(c, self.store.campaign_id)
                    ).controller
                    != viewer.user_id
                ):
                    eligible_reign.append(item)
            tags += [item.model_dump(mode="json") for item in eligible_reign]
            result = dict(row) | {
                "body": body,
                "play": action["data"]["play"],
                "result": action["data"]["result"],
                "actor": actor.owner,
                "tags": tags,
                "reign_enemy_tag_ids": [item.id for item in eligible_reign],
                "own": own_data,
                "participants": action["data"]["participants"],
                "pilots": [
                    uid for uid in action["data"]["participants"] if str(uid) in state.sheets
                ],
                "labels": {
                    str(uid): state.sheets[str(uid)].callsign
                    for uid in action["data"]["participants"]
                    if str(uid) in state.sheets
                },
                "parent": action["id"],
                "channel": int(action["channel_id"]),
                "order_text": action["data"].get("order_text"),
                "context": action["data"].get("context"),
                "prepared": {
                    k: v
                    for k, v in action["data"].get("prepared", {}).items()
                    if k in ("order_id", "target")
                },
            }
            if learned_keep_rule is not None:
                result["learned_keep_rule"] = learned_keep_rule
            if row["kind"] == "tag_window" and decision_owner == actor.owner:
                from girlframe.services.m3_learned_plays import hound_status_available

                if hound_status_available(self, c, state, action, decision_owner):
                    result["learned_hound_available"] = True
            if row["kind"] in ("order_response", "order_disobey"):
                from girlframe.services.m3_bonded_rejection import order_projection

                rejection_order = order_projection(self, c, viewer, state, action, row)
                if rejection_order is not None:
                    result["bonded_rejection_order"] = rejection_order
                    body["source_work"] = rejection_order["source_work"]
                    body["context"] = rejection_order["context"]
            if row["kind"] == "order_response":
                from girlframe.engine.m3_actor_bonds import current_ref as am_order_original
                from girlframe.engine.m3_am import free as am_free

                result["am_can_refuse"] = am_free(
                    state, am_order_original(state, int(action["actor_id"])), "refuse"
                )
            if action["data"].get("npc_order"):
                from girlframe.engine.m3_actors import resolve as resolve_npc_issuer
                from girlframe.services.m3_npc_orders import order as original_npc_order

                issuer = original_npc_order(self, c, action).issuer
                result["npc_order_issuer"] = resolve_npc_issuer(state, issuer, ()).label
            if action["data"].get("beneath") and row["kind"].startswith("beneath_"):
                from girlframe.services.m3_beneath import projection

                result["beneath"] = projection(self, c, viewer, state, action, dict(row))
            if action["data"].get("defeat") and row["kind"].startswith("defeat_"):
                from girlframe.services.m3_defeat import projection as defeat_projection

                result["defeat"] = defeat_projection(self, c, state, action, dict(row))
            if action["data"].get("dive") and row["kind"].startswith("dive_"):
                from girlframe.services.m3_dive import projection as dive_projection

                result["dive"] = dive_projection(self, c, viewer, state, action, dict(row))
            if action["data"].get("battle") and row["kind"].startswith("battle_"):
                from girlframe.services.m3_battle import projection as battle_projection

                result["battle"] = battle_projection(self, c, state, action, dict(row))
            if row["kind"] in (
                "enforcer_firepower",
                "enforcer_firepower_context",
                "enforcer_firepower_confirm",
            ):
                from girlframe.services.m3_enforcer_firepower import (
                    projection as firepower_projection,
                )

                result["enforcer_firepower"] = firepower_projection(
                    self, c, state, action, dict(row)
                )
            if (
                row["kind"].startswith("mockingbird_")
                and row["kind"] not in ("mockingbird_risk", "mockingbird_void_threshold")
                and action["data"].get("mockingbird")
            ):
                from girlframe.services.m3_mockingbird_plays import (
                    projection as mock_play_projection,
                )

                result["mockingbird_play"] = mock_play_projection(self, c, state, action, dict(row))
            if row["kind"] in ("mockingbird_risk", "mockingbird_void_threshold"):
                from girlframe.services.m3_mockingbird import projection as mockingbird_projection

                result["mockingbird"] = mockingbird_projection(self, c, state, action, dict(row))
            if row["kind"].startswith("engage_"):
                from girlframe.services.m3_engage import projection as engage_projection

                result["engage"] = engage_projection(self, c, state, action, dict(row))
            if row["kind"] == "budget_asset_calamity":
                from girlframe.services.m3_budget_sabotage import projection as sabotage_projection

                result["asset_calamities"] = sabotage_projection(self, c, state, action)
            if action["data"].get("engage") and row["kind"].startswith("battle_"):
                from girlframe.services.m3_battle import damage_projection

                result["battle"] = damage_projection(self, c, state, action, dict(row))
            if action["data"].get("enforcement") and row["kind"].startswith("enforcer_"):
                from girlframe.services.m3_enforcement_initiative import (
                    projection as enforcement_projection,
                )

                result["enforcement"] = enforcement_projection(
                    self, c, viewer, state, action, dict(row)
                )
            if action["data"].get("enforcer_keep"):
                result["enforcer_keep"] = action["data"]["enforcer_keep"]
            if row["kind"] == "actor_sensors":
                from girlframe.services.p1_consume_hooks import smell_question

                result["consume_smell"] = smell_question(self, c, state, action)
            if row["kind"] == "order_response":
                from girlframe.engine.m3_consume import feral_effects
                from girlframe.services.m3_consume import acting as consume_actor

                original = consume_actor(state, action)
                result["consume_order_tags"] = (
                    [
                        dict(id=x.tag, name=x.label)
                        for x in feral_effects(state, original)
                        if x.tier in ("mid", "high")
                    ]
                    if original
                    else []
                )
            if row["kind"] == "actor_disobey":
                from girlframe.services.m3_alpha import removable as removable_broken

                result["alpha_remove_broken"] = removable_broken(self, c, state, action) is not None
            if row["kind"] == "tag_window":
                from girlframe.services.m3_gender_designation import man_tag_options

                result["gender_man_tags"] = man_tag_options(self, c, state, action, viewer.user_id)
            if row["kind"] == "tag_window":
                from girlframe.services.m3_tag_markers import projection as marker_projection

                result["tag_markers"] = marker_projection(self, c, state, action, decision_owner)
                from girlframe.services.m3_tag_markers import current as actual_markers
                from girlframe.services.p1_consume_hooks import starvation

                result["consume_starvation"] = any(
                    starvation(self, c, state, action, x.actor) is not None
                    for x in actual_markers(self, c, state, action, decision_owner)
                )
            if action["data"].get("nightmare_core") and row["kind"] in (
                "actor_keep",
                "handler_keep",
            ):
                from girlframe.services.m3_nightmare import automatic as nightmare_automatic

                result["nightmare_core"] = bool(nightmare_automatic(action))
            if action["data"].get("kicked_puppy") and row["kind"] == "actor_flirt":
                from girlframe.services.m3_kicked_puppy import questions as kicked_questions

                result["flirt_questions"] = kicked_questions(self, c, state, action)
            if row["kind"] in ("tag_marker_selection", "tag_marker_agreement"):
                from girlframe.services.m3_tag_markers import discussion_projection

                result["tag_marker_discussion"] = discussion_projection(
                    self, c, state, action, viewer.user_id
                )
            if row["kind"] in ("actor_keep", "handler_keep") and action["data"].get(
                "cute_uniforms"
            ):
                result["cute_uniforms"] = action["data"]["cute_uniforms"]
            if row["kind"] == "tag_resolution" and str(body.get("tag", "")).startswith(
                "cute-uniform:"
            ):
                from girlframe.engine.m3_assets import can_replace_at_limit
                from girlframe.services.m3_cute_uniforms import prove_tag

                uniform = next(x for x in uniform_tags(state, actor.owner) if x.id == body["tag"])
                prove_tag(self, c, state, actor.owner, uniform)
                result["cute_uniform_tag"] = True
                result["cute_uniform_replacements"] = [
                    dict(id=x.id, name=x.name)
                    for x in actor.assets
                    if x.family == "girl" and not x.void and can_replace_at_limit(actor, x)
                ]
            from girlframe.engine.m3_beneath import rejection_blocked

            if row["kind"] == "order_response":
                from girlframe.engine.m3_actor_bonds import current_ref as gender_ref
                from girlframe.engine.m3_gender_designation import current as designation

                order_table = t.m2["m2_orders"]
                gender_issuer = c.scalar(
                    sa.select(order_table.c.issuer_id).where(
                        order_table.c.campaign_id == self.store.campaign_id,
                        order_table.c.id == action["data"].get("order_id"),
                    )
                )
                if gender_issuer is not None and str(gender_issuer) in state.sheets:
                    speaker = designation(state, gender_ref(state, viewer.user_id))
                    addressee = designation(state, gender_ref(state, int(gender_issuer)))
                    result["gender_spoken_no"] = bool(
                        speaker is not None
                        and speaker.gender == "woman"
                        and addressee is not None
                        and addressee.gender == "man"
                    )
            result["rejection_blocked"] = bool(
                row["kind"] == "tag_resolution"
                and rejection_blocked(state, int(action["actor_id"]), body["tag"])
            )
            return result

    def recover_helpless(
        self, viewer: GuildViewer, key: str, revision: int, context: str, asset: str | None
    ) -> dict[str, Any]:
        if not context.strip() or len(context) > 1200:
            raise WorkflowError("Describe the moment alone in which you compose yourself.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            from girlframe.engine.m3_actor_bonds import clear_helpless, current_ref, is_helpless

            if (
                sheet is None
                or sheet.revision != revision
                or not is_helpless(state, current_ref(state, viewer.user_id))
            ):
                raise WorkflowError("STALE_SHEET: no matching Helpless recovery is available.")
            scenes = t.m2["m2_scenes"]
            for row in c.execute(
                sa.select(scenes).where(
                    scenes.c.campaign_id == self.store.campaign_id, scenes.c.open.is_(True)
                )
            ).mappings():
                if viewer.user_id in json.loads(row["participants_json"]):
                    lock = self.lock(c, row["channel_id"])
                    if lock and lock["state"] != "released":
                        raise WorkflowError(
                            "Resolve the immediate scene action before taking a moment alone."
                        )
            girls = [x for x in sheet.assets if x.family == "girl"]
            if girls and all(x.damaged for x in girls):
                chosen = next((x for x in girls if x.id == asset), None)
                if chosen is None:
                    raise WorkflowError("Choose one damaged Girl Asset to recover.")
                chosen.damaged = False
            elif asset is not None:
                raise WorkflowError("Recover an Asset only if all Girl Assets are damaged.")
            sheet.revision += 1
            response_event = str(uuid4())
            from girlframe.services.m3_oldgen_sex import recover_helpless as recover_oldgen_sex

            state = clear_helpless(state, current_ref(state, viewer.user_id), response_event)
            recover_oldgen_sex(self, c, state, current_ref(state, viewer.user_id), response_event)
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.helpless_recovered",
                state,
                event_id=response_event,
                owner=viewer.user_id,
            )
            return {"owner": viewer.user_id, "revision": sheet.revision}

        return self.store._write(
            viewer,
            key,
            "m2.helpless_recovered",
            {"revision": revision, "context": context, "asset": asset},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def depart_doll(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        source: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        from girlframe.services.m3_cast import change_doll_presence

        return change_doll_presence(
            self, viewer, key, channel, source, revision, account, returning=False
        )

    def return_doll(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        source: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        from girlframe.services.m3_cast import change_doll_presence

        return change_doll_presence(
            self, viewer, key, channel, source, revision, account, returning=True
        )

    def leave_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            scene = self.scene(c, channel)
            from girlframe.services.p1_source_pause import require_clear as require_source_clear

            require_source_clear(self, c, channel)
            state = load_state(c, self.store.campaign_id)
            if any(x.id == scene["id"] and x.open for x in state.scene_casts):
                raise WorkflowError("Withdraw your actual role through /mission cast.")
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Resolve the pending Play before leaving this scene.")
            people = [x for x in scene["participants"] if x != viewer.user_id]
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=scene["revision"] + 1)
            )
            self.event(c, viewer.user_id, key, "m2.scene_left", channel=channel)
            return {"channel": channel, "participants": people}

        return self.store._write(
            viewer,
            key,
            "m2.scene_left",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )
