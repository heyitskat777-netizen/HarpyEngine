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
            if sheet.owner == viewer.user_id:
                from girlframe.engine.m3_clone_am import additional_identities
                from girlframe.services.m3_clone_am import prove_additional

                additional = additional_identities(state, sheet.owner)
                if additional:
                    prove_additional(self, c, state, sheet.owner)
                data["additional_identities"] = [x.model_dump(mode="json") for x in additional]
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
            self.event(
                c, viewer.user_id, key, "m2.character_activated", state, owner=viewer.user_id
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
            *M3_HEAT_IDS,
            *M3_ASSET_IDS,
            *JANUS_ROLL_IDS,
        ):
            raise WorkflowError("UNSUPPORTED_RULE: this Play is not implemented in M2.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
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
            am_scrutinized = None
            am_code = None
            alpha_sex_counter_scope = None
            alpha_counter_scope = None
            npc_order_scope = None
            void_keep = None
            dormant_dive_source = None
            from girlframe.services.m3_gorgon_play import (
                prepare_response as prepare_gorgon_response,
            )

            gorgon_response = prepare_gorgon_response(self, c, viewer, prepared, state, channel)
            from girlframe.services.m3_beneath import no_conflict

            no_conflict(self, c, viewer, prepared)
            if prepared.play in M3_ASSET_IDS:
                from girlframe.services.m3_defeat import prepare as prepare_defeat

                defeat = prepare_defeat(self, c, viewer, prepared, state)
            elif prepared.play == "keep_your_head" and prepared.source_work is not None:
                from girlframe.services.m3_void_keep import prepare_keep

                void_keep, state = prepare_keep(self, c, viewer, prepared, state, channel)
            elif prepared.play == "dive_deep" and prepared.source_work is not None:
                from girlframe.services.m3_battle_dormant import prepare_dive_source

                dormant_dive_source = prepare_dive_source(self, c, viewer, prepared, state, channel)
            elif prepared.play in ("mockingbird_person", "mockingbird_sex"):
                from girlframe.services.m3_mockingbird_plays import prepare as prepare_mockingbird

                mockingbird = prepare_mockingbird(self, c, viewer, prepared, state, channel=channel)
            elif prepared.source_work is not None and prepared.play not in (
                "alpha_sex",
                "am_scrutinized",
                "am_just_code",
            ):
                raise WorkflowError("A source work reference belongs to its actual mandatory Play.")
            if prepared.play in ("all_out_assault", "go_for_the_core"):
                from girlframe.engine.m3_actor_state import ActorRef
                from girlframe.services.m3_battle import prepare as prepare_battle

                battle = prepare_battle(self, c, viewer, state, self.scene(c, channel), prepared)
                actual_battle_actor = ActorRef.model_validate(battle["actor"])
                if (
                    actual_battle_actor.kind != "pilot"
                    or actual_battle_actor.entity != str(viewer.user_id)
                    or actual_battle_actor.incarnation
                    != self.character_binding(
                        c, state, viewer.user_id, require_current_profile=False
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
                from girlframe.services.m3_engage import prepare as prepare_engage

                engage = prepare_engage(self, c, viewer, state, self.scene(c, channel), prepared)
            if prepared.play in JANUS_ROLL_IDS:
                from girlframe.services.m3_janus_play import prepare as prepare_janus

                janus = prepare_janus(self, c, viewer, prepared, state, channel=channel)
            if prepared.play == "am_just_code":
                from girlframe.services.m3_am_code import prepare as prepare_am_code

                am_code = prepare_am_code(self, c, viewer, state, prepared, channel)
            if prepared.play == "am_scrutinized":
                from girlframe.services.m3_am_scrutinized import prepare as prepare_am

                am_scrutinized = prepare_am(self, c, viewer, state, prepared, channel)
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
                        self, c, alpha_source, alpha_response_ref(state, viewer.user_id), prepared
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
                        self, c, sex_parent, sex_response_ref(state, viewer.user_id), prepared
                    )
                    alpha_sex_counter_scope = sex_parent["data"]["alpha_sex"]
            from girlframe.services.m3_npc_orders import prepare as prepare_npc_order

            npc_order_scope = prepare_npc_order(self, c, state, viewer, channel, prepared)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or sheet.revision != sheet_revision:
                raise WorkflowError("STALE_SHEET: refresh the Play wizard.")
            if any(x.get("kind") == "alpha_sex_session" for x in state.facts):
                from girlframe.engine.m3_actor_bonds import current_ref as sleeping_original
                from girlframe.engine.m3_alpha_sex import require_awake

                require_awake(state, sleeping_original(state, viewer.user_id))
            if sheet.frame_scrapped and prepared.piloting and defeat is None:
                raise WorkflowError(
                    "REQUIRED_FOLLOWUP: replace the scrapped Frame before new Plays."
                )
            from girlframe.services.m3_virus_orders import required_disobey

            virus_order_work = required_disobey(self, c, viewer, state, prepared, channel)
            if (
                self.immediate_work(
                    c,
                    viewer.user_id,
                    scene_id=self.scene(c, channel)["id"],
                    excluding=frozenset({virus_order_work}) if virus_order_work else frozenset(),
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
                entity=str(viewer.user_id),
                incarnation=self.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
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
            self.character_binding(c, state, viewer.user_id)
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
                        am_scrutinized,
                        am_code,
                        alpha_sex_counter_scope,
                        alpha_counter_scope,
                        npc_order_scope,
                        gorgon_response,
                    )
                )
                and not scoped_defeat
            ):
                self.pilot_cast(
                    c,
                    state,
                    scene,
                    owners=(viewer.user_id,) + ((prepared.target,) if prepared.target else ()),
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
                elif gorgon_response is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(gorgon_response["cast"]))
                elif scoped_defeat:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    source_cast, _ = CastService(ActorService(MissionService(self.store)))._current(
                        c, state, channel
                    )
                elif npc_order_scope is not None:
                    source_cast = SceneCast.model_validate_json(json.dumps(npc_order_scope["cast"]))
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
                    {role.controller for role in source_cast.roles if role.actor.kind == "pilot"}
                    | {source_cast.facilitator}
                ):
                    raise WorkflowError(
                        "STALE_CAST: recover the actual Dive participants and facilitator."
                    )
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.services.m3_scene_requisitions import guard as guard_private_scene

            acting_ref = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
                ),
            )
            from girlframe.engine.m3_am import require_freedom, require_harm

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
                viewer.user_id not in scene["participants"]
                or state.handler not in scene["participants"]
            ):
                raise WorkflowError("The acting Pilot and Handler must explicitly join this scene.")
            root_lock = self.lock(c, channel)
            parent = None
            counter_source = None
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
                        if x["kind"]
                        in (
                            "escape_play",
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
                            "battle_dormant_dive",
                            "battle_dormant_threshold",
                            "mockingbird_void_threshold",
                            "mockingbird_sex_void_threshold",
                            "janus_void_threshold",
                            "snoop_item_void_threshold",
                            "gorgon_response_play",
                        )
                        and x["actor_id"] == str(viewer.user_id)
                    ),
                    None,
                )
                if required is None:
                    raise WorkflowError("Only the required player can make this response Play.")
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
                        entity=str(viewer.user_id),
                        incarnation=self.character_binding(
                            c, state, viewer.user_id, require_current_profile=False
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
                        entity=str(viewer.user_id),
                        incarnation=self.character_binding(
                            c, state, viewer.user_id, require_current_profile=False
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
                    am_scrutinized,
                    am_code,
                    doctor,
                )
            ):
                raise WorkflowError("This implemented Play does not take a fictional actor target.")
            if prepared.play in ("flirt", "put_someone_beneath_you"):
                if (
                    prepared.target == viewer.user_id
                    or str(prepared.target) not in state.sheets
                    or prepared.target not in scene["participants"]
                ):
                    raise WorkflowError("Choose another active human Pilot in this scene.")
            elif prepared.target is not None:
                raise WorkflowError("This implemented Play does not take a Pilot target.")
            if prepared.play == "engage" and not any(not x.damaged for x in sheet.assets):
                raise WorkflowError("No legal undamaged Asset is available for Engage.")
            if prepared.play == "disobey_orders":
                self.valid_order(c, state, viewer.user_id, channel, prepared.order_id)
            kicked_puppy = None
            if prepared.play == "flirt" or prepared.kicked_puppy_basis:
                from girlframe.services.m3_kicked_puppy import prepare as prepare_kicked_puppy

                kicked_puppy = prepare_kicked_puppy(self, c, viewer, state, prepared)
            nightmare_core = None
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_nightmare import prepare as prepare_nightmare

                nightmare_core = prepare_nightmare(self, c, viewer, state, prepared)
            from girlframe.services.m3_cute_uniforms import prepare_keep as prepare_cute_keep

            cute_uniforms = prepare_cute_keep(self, c, viewer, state, prepared)
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
            from girlframe.services.m3_recovery import enable as enable_recovery

            enable_recovery(self, c, viewer, data)
            if prepared.play == "disobey_orders":
                from girlframe.services.m3_refusal import prepare as prepare_refusal

                data["m3_refusal"] = prepare_refusal(self, c, viewer, state)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
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
            appearance_reset = False
            if m3 is not None and prepared.play in ("go_off_duty", "void_observation"):
                from girlframe.engine.m3_appearance_matrix import reset_at_start

                appearance_reset = reset_at_start(state, acting_ref, m3["period_id"], identity)
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
                    void_keep is not None
                    or alpha_sex is not None
                    or am_scrutinized is not None
                    or am_code is not None
                    or appearance_reset
                )
                else None,
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
        source_authority = False
        if row is not None and json.loads(row["body_json"]).get("succubus"):
            from girlframe.services.m3_succubus import valid_order as valid_succubus_order

            source_authority = valid_succubus_order(self, c, state, dict(row))
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
            if action["actor_id"] != str(viewer.user_id):
                raise WorkflowError("Only the acting Pilot can confirm this roll.")
            if action["data"]["receipt"]:
                return {"action_id": identity, "receipt": action["data"]["receipt"]}
            if action["data"].get("gorgon_play", {}).get("started"):
                return {"action_id": identity, "receipt": None}
            self.unpaused(c)
            lock = self.lock(c, action["channel_id"])
            if (
                not lock
                or lock["state"] != "held"
                or action["state"] not in ("acquiring", "ready_to_roll")
            ):
                raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no dice or Heat were consumed.")
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
                *M3_HEAT_IDS,
                *M3_ASSET_IDS,
                *JANUS_ROLL_IDS,
            ):
                raise WorkflowError("This action is diceless.")
            state = load_state(c, self.store.campaign_id)
            self.action_characters(c, action, state)
            if action["data"].get("void_keep"):
                from girlframe.services.m3_void_keep import authorize_keep

                authorize_keep(self, c, state, action)
            if HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("STALE_HANDLER: staff recovery is required.")
            sheet = state.sheets[str(viewer.user_id)]
            if sheet.revision != action["data"]["sheet_revision"]:
                raise WorkflowError("STALE_SHEET: recover the unrolled action; no dice consumed.")
            prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_nightmare import pre_roll as nightmare_pre_roll

                nightmare_pre_roll(self, c, viewer, state, action)
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
                    c, state, viewer.user_id, int(action["channel_id"]), prepared.order_id
                )
            if action["data"].get("am_code"):
                from girlframe.services.m3_am_code import pre_roll as pre_roll_am_code

                pre_roll_am_code(self, c, viewer, state, action)
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import pre_roll as pre_roll_am

                pre_roll_am(self, c, viewer, state, action)
            if prepared.play == "disobey_orders":
                from girlframe.engine.m3_actor_bonds import current_ref as am_original
                from girlframe.engine.m3_am import require_freedom

                require_freedom(state, am_original(state, viewer.user_id), "refuse")
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
                sheet = state.sheets[str(viewer.user_id)]
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
            if prepared.identity:
                from girlframe.engine.m3_clone_am import mark_additional
                from girlframe.services.m3_clone_am import prove_additional

                prove_additional(self, c, state, sheet.owner, prepared.identity)
                share = mark_additional(
                    state, sheet, prepared.identity, prepared.gain, prepared.pair_share
                )
                if share is None:
                    share = mark_identity(
                        sheet, prepared.identity, prepared.gain, prepared.pair_share, state=state
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
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
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
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
                or action["data"].get("dampener")
                or action["data"].get("kicked_puppy")
                or action["data"].get("nightmare_core")
                or action["data"].get("cute_uniforms")
                or action["data"].get("cute_uniform_tags")
                or action["data"].get("cute_uniform_rejection")
                or defeat is not None
                else "m2.rolled",
                state,
                event_id=defeat["roll_event"]
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
                else None,
                action_id=identity,
                receipt_id=receipt["id"],
            )
            if m3 is not None:
                from girlframe.services.m3_play_support import save_raw_roll

                save_raw_roll(self, c, action, state, event)
            if action["data"].get("doctor"):
                from girlframe.services.m3_doctor import synchronize as synchronize_doctor

                synchronize_doctor(self, c, action, event)
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

    def choices(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            table = t.m2["m2_choices"]
            return [
                dict(x)
                for x in c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.actor_id == str(viewer.user_id),
                        table.c.state == "pending",
                    )
                ).mappings()
            ]

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
                        table.c.actor_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision belongs to another player or is unavailable.")
            action = self.action(c, row["action_id"])
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self).authorize(c, viewer, action)
                return dict(row)
            if row["kind"] == "budget_asset_calamity":
                from girlframe.services.m3_access import Access

                Access(self.store).authorize(c, viewer, "strain")
            director_tag_response = False
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
                or action["data"].get("am_scrutinized")
                or action["data"].get("am_code")
                or action["data"].get("npc_order")
                or action["data"].get("gorgon_play")
                else "m2.choice_resolved",
                state,
                event_id=action["data"]["response_event"],
                action_id=action["id"],
                choice_id=choice_id,
            )
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
            if action["data"].get("mockingbird"):
                from girlframe.services.m3_mockingbird_plays import (
                    post_synchronize as post_mockingbird,
                )

                post_mockingbird(self, c, action, event, viewer, key)
            if action["data"].get("am_scrutinized"):
                from girlframe.services.m3_am_scrutinized import synchronize as synchronize_am

                synchronize_am(self, c, action, event)
            if action["data"].get("alpha_sex"):
                from girlframe.services.m3_alpha_sex import synchronize as synchronize_alpha_sex

                synchronize_alpha_sex(self, c, action, event)
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
        self, viewer: GuildViewer, key: str, channel: int, target: int, text: str
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
            authority = None
            if not higher(state, viewer.user_id, target):
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
                        {"text": text} | ({"succubus": authority} if authority else {})
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
            self.event(c, viewer.user_id, key, "m2.order_issued", action_id=identity)
            return {"action_id": identity, "order_id": order_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.order_issued",
                {"channel": channel, "target": target, "text": text},
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
            self.event(
                c, viewer.user_id, key, "m2.scene_closed", state if cast else None, channel=channel
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
            from girlframe.engine.m3_deep_brain_spikes import scene_context

            return {
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
                        table.c.actor_id == str(viewer.user_id),
                        table.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision is no longer available to you.")
            if row["kind"] == "battle_sprite_intercept":
                from girlframe.services.m3_sprite import SpriteService

                return SpriteService(self.store).decision(viewer, choice_id)
            action = self.action(c, row["action_id"])
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
            own = state.sheets.get(str(viewer.user_id))
            # Return only selectable entities needed by this decision, never another private sheet.
            body = json.loads(row["body_json"])
            from girlframe.services.m3_cute_uniforms import tags as uniform_tags

            tags = [
                x.model_dump(mode="json")
                for x in actor.tags + uniform_tags(state, actor.owner)
                if viewer.user_id in x.observers or viewer.user_id == actor.owner
            ]
            if (
                action["data"].get("kicked_puppy")
                and row["kind"] == "tag_window"
                and viewer.user_id == actor.owner
            ):
                from girlframe.engine.m3_girl_runtime_state import has_rule as kicked_has_rule
                from girlframe.engine.m3_girl_runtime_state import mentor_tag as kicked_mentor_tag
                from girlframe.services.m3_kicked_puppy import self_tag as kicked_self_tag

                tags = [
                    x.model_dump(mode="json")
                    for x in actor.tags + uniform_tags(state, actor.owner)
                    if kicked_self_tag(self, c, state, action, viewer.user_id, x)
                    or kicked_mentor_tag(actor, x, state)
                    or kicked_has_rule(actor, "girl.princess.objectively-beautiful", "PRINCESS")
                ]
            if viewer.user_id == actor.owner and row["kind"] == "tag_window":
                from girlframe.services.m3_control_ritual import candidates as ritual_candidates

                tags += [
                    x.model_dump(mode="json") for x in ritual_candidates(state, action, actor.owner)
                ]
            own_data = own.model_dump(mode="json") if own else None
            if own is not None and own_data is not None:
                from girlframe.engine.m3_clone_am import additional_identities
                from girlframe.services.m3_clone_am import prove_additional

                additional = additional_identities(state, own.owner)
                if additional:
                    prove_additional(self, c, state, own.owner)
                own_data["additional_identities"] = [x.model_dump(mode="json") for x in additional]
                own_data["tags"] += [
                    x.model_dump(mode="json") for x in uniform_tags(state, own.owner)
                ]
            result = dict(row) | {
                "body": body,
                "play": action["data"]["play"],
                "result": action["data"]["result"],
                "actor": actor.owner,
                "tags": tags,
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
            if row["kind"] == "actor_disobey":
                from girlframe.services.m3_alpha import removable as removable_broken

                result["alpha_remove_broken"] = removable_broken(self, c, state, action) is not None
            if row["kind"] == "tag_window":
                from girlframe.services.m3_tag_markers import projection as marker_projection

                result["tag_markers"] = marker_projection(self, c, state, action, viewer.user_id)
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
            state = clear_helpless(state, current_ref(state, viewer.user_id), response_event)
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

    def leave_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            scene = self.scene(c, channel)
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
